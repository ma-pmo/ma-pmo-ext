"""Replay evaluator: would a workflow step do as well on the fast model, and save money?

`replay()` runs the workflow as it is in use and again with one step on the fast tier, each
`repeat` times, alternating, on the demo data in a throwaway workspace (core/sandbox.py). For
that step it measures, per run:

- cost: the step's USD in the cost ledger;
- valid output: the share of the step's structured LLM calls that produced a schema-valid answer
  (first try or after the one retry) rather than falling back;
- risk accuracy (risk steps only): the share of risk alerts whose severity agrees with the
  labelled outcome in `fixtures/risk_ground_truth.json` (medium or above is a risk).

It reports the difference for each with a 95% bootstrap confidence interval and a verdict:
`recommended` only if no quality measure can be worse by more than `tolerance` (the interval's
lower end) and the saving is above zero (the interval's lower end); `inconclusive` when there is
no LLM output to compare (no API key, or every call fell back). Nothing changes: a person
approves a recommendation, which makes a draft of the workflow; publishing it is separate.

The replay spends real money when an LLM is configured. That spend is kept in this workspace's
ledger (`purpose` "replay") and the workspace's budgets apply to it.
"""
from __future__ import annotations

import json
import random
import statistics
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select

from ma_pmo.core import llm, runs, scenarios, workflow_store
from ma_pmo.core.i18n import tr
from ma_pmo.core.obs import get_logger
from ma_pmo.core.sandbox import demo_scope, sandbox
from ma_pmo.core.workflow import WorkflowSpec
from ma_pmo.db.init import LESSONS
from ma_pmo.db.models import AgentMessageRow, LlmCall, Recommendation
from ma_pmo.db.session import get_session

_log = get_logger("replay")
RECOMMENDED, NOT_RECOMMENDED, INCONCLUSIVE = "recommended", "not_recommended", "inconclusive"
PROPOSED, APPROVED, REJECTED = "proposed", "approved", "rejected"
RESAMPLES, SEED = 2000, 7
_POSITIVE = {"medium", "high", "critical"}


def _labels() -> dict[str, str]:
    path = LESSONS.parent / "risk_ground_truth.json"
    return dict(json.loads(path.read_text(encoding="utf-8"))["labels"])


def _with_tier(spec: WorkflowSpec, step_id: str, tier: str | None) -> WorkflowSpec:
    steps = [s.model_copy(update={"model_tier": tier}) if s.id == step_id else s
             for s in spec.steps]
    return spec.model_copy(update={"steps": steps})


def _one_run(spec: WorkflowSpec, step_id: str, labels: dict[str, str]) -> dict:
    seq = next(i for i, s in enumerate(spec.steps, start=1) if s.id == step_id)
    with llm.observe() as outcomes:
        try:
            run_id = scenarios.run_spec(spec, demo_scope())["run_id"]
        except Exception:  # a failing agent is a result too
            _log.exception("replay_run_failed", workflow=spec.id)
            run_id = runs.list_runs(limit=1)[0]["run_id"]
    mine = [o for o in outcomes if o["run_id"] == run_id and o["step"] == seq]
    tried = [o for o in mine if o["outcome"] != llm.UNAVAILABLE]
    good = [o for o in tried if o["outcome"] in (llm.VALID, llm.RETRIED)]
    with get_session() as s:
        usd, calls, unpriced = s.execute(select(
            func.coalesce(func.sum(LlmCall.usd), 0.0), func.count(LlmCall.id),
            func.count(LlmCall.id) - func.count(LlmCall.usd)).where(
            LlmCall.run_id == run_id, LlmCall.step_seq == seq)).one()
        alerts = [m.payload.get("data", {}) for m in s.scalars(select(AgentMessageRow).where(
            AgentMessageRow.run_id == run_id,
            AgentMessageRow.dedupe_key.like(f"{run_id}:{seq}:%")))
            if m.payload.get("schema") == "risk_alert.v1"]
    judged = [a for a in alerts if a.get("project_id") in labels]
    right = [a for a in judged if (a.get("severity") in _POSITIVE)
             == (labels[a["project_id"]] in _POSITIVE)]
    return {"run_id": run_id, "usd": float(usd), "calls": int(calls), "unpriced": int(unpriced),
            "structured_calls": len(tried),
            "valid_output": len(good) / len(tried) if tried else None,
            "risk_accuracy": len(right) / len(judged) if judged and tried else None,
            "budget_fallback": runs.get_state(run_id).get("budget") is not None}


def _interval(base: list[float], cand: list[float]) -> dict | None:
    """Difference of means (candidate - baseline) with a 95% bootstrap interval."""
    if len(base) < 2 or len(cand) < 2:
        return None
    rng = random.Random(SEED)
    diffs = sorted(statistics.fmean(rng.choices(cand, k=len(cand)))
                   - statistics.fmean(rng.choices(base, k=len(base))) for _ in range(RESAMPLES))
    low, high = diffs[int(0.025 * RESAMPLES)], diffs[int(0.975 * RESAMPLES) - 1]
    return {"baseline": round(statistics.fmean(base), 6),
            "candidate": round(statistics.fmean(cand), 6),
            "delta": round(statistics.fmean(cand) - statistics.fmean(base), 6),
            "ci95": [round(low, 6), round(high, 6)], "n": [len(base), len(cand)]}


def _verdict(quality: dict[str, dict | None], cost: dict | None,
             tolerance: float) -> tuple[str, list[dict]]:
    """The verdict and why, as codes (see `reason_text`) so each reader gets their language."""
    measured = {k: v for k, v in quality.items() if v is not None}
    if not measured:
        return INCONCLUSIVE, [{"code": "no_output"}]
    reasons: list[dict] = [{"code": "quality_drop", "metric": k, "tolerance": tolerance}
                           for k, v in measured.items() if v["ci95"][0] < -tolerance]
    saving = None if cost is None else -cost["ci95"][1]  # the smallest saving the data allows
    if saving is None or saving <= 0:
        reasons.append({"code": "no_saving"})
    if reasons:
        return NOT_RECOMMENDED, reasons
    return RECOMMENDED, [{"code": "holds", "tolerance": tolerance}]


def reason_text(reason: dict) -> str:
    code, tol = reason["code"], reason.get("tolerance", 0.0)
    if code == "no_output":
        return tr("no LLM output to compare: the step made no LLM call, or every call fell back "
                  "(is an API key set?)",
                  "비교할 LLM 출력이 없습니다. 이 단계가 LLM을 호출하지 않았거나 모든 호출이 "
                  "대체 방식으로 처리되었습니다(API 키가 있나요?)")
    if code == "quality_drop":
        return tr(f"{reason['metric']} may drop by more than {tol:.0%}",
                  f"{reason['metric']}: {tol:.0%}보다 더 떨어질 수 있습니다")
    if code == "no_saving":
        return tr("no saving that the data can show", "데이터로 확인되는 절감이 없습니다")
    return tr(f"quality holds within {tol:.0%} and the step costs less",
              f"품질이 {tol:.0%} 안에서 유지되고 이 단계의 비용이 줄어듭니다")


def replay(workflow_id: str, step_id: str, *, repeat: int = 3, tolerance: float = 0.05,
           by: str = "") -> dict:
    """Replay one step on the fast tier and store the recommendation. Raises KeyError/ValueError."""
    if not 2 <= repeat <= 50:
        raise ValueError(tr("repeat must be between 2 and 50",
                            "반복 횟수는 2에서 50 사이여야 합니다"))
    spec = scenarios.workflow(workflow_id)
    step = next((s for s in spec.steps if s.id == step_id), None)
    if step is None:
        raise KeyError(f"{workflow_id}/{step_id}")
    if step.model_tier == "fast":
        raise ValueError(tr("this step already uses the fast model",
                            "이 단계는 이미 빠른 모델을 씁니다"))
    candidate, labels = _with_tier(spec, step_id, "fast"), _labels()
    base_runs: list[dict] = []
    cand_runs: list[dict] = []
    with sandbox("replay"):
        for _ in range(repeat):  # alternate, so drift over time hits both sides alike
            base_runs.append(_one_run(spec, step_id, labels))
            cand_runs.append(_one_run(candidate, step_id, labels))

    def values(rows: list[dict], key: str) -> list[float]:
        return [r[key] for r in rows if r[key] is not None]

    quality = {k: _interval(values(base_runs, k), values(cand_runs, k))
               for k in ("valid_output", "risk_accuracy")}
    cost = _interval([r["usd"] for r in base_runs], [r["usd"] for r in cand_runs])
    verdict, reasons = _verdict(quality, cost, tolerance)
    report = {
        "workflow": workflow_id, "step": step_id, "agent": step.agent,
        "base_version": spec.version, "repeat": repeat, "tolerance": tolerance,
        "models": {"baseline": llm.model_for(step.model_tier),
                   "candidate": llm.model_for("fast")},
        "cost": cost, "quality": quality, "reasons": reasons,
        "saving_pct": (round(-cost["delta"] / cost["baseline"] * 100, 1)
                       if cost and cost["baseline"] else None),
        "stopped_by_budget": any(r["budget_fallback"] for r in base_runs + cand_runs),
        "runs": {"baseline": base_runs, "candidate": cand_runs},
    }
    with get_session() as s:
        row = Recommendation(workflow_id=workflow_id, step_id=step_id, base_version=spec.version,
                             verdict=verdict, report=report, created_by=by)
        s.add(row)
        s.flush()
        return _row(row)


def recommendations() -> list[dict]:
    with get_session() as s:
        return [_row(r) for r in s.scalars(select(Recommendation)
                                           .order_by(Recommendation.id.desc()))]


def decide(rec_id: int, decision: str, by: str) -> dict:
    """Approve (which makes a draft of the workflow) or reject a proposed recommendation."""
    with get_session() as s:
        row = s.get(Recommendation, rec_id)
        if row is None:
            raise KeyError(rec_id)
        if row.status != PROPOSED:
            raise ValueError(tr(f"already {row.status}", f"이미 {row.status} 상태입니다"))
        if decision == APPROVED and row.verdict != RECOMMENDED:
            raise ValueError(tr("only a recommended change can be approved; reject this one",
                                "추천된 변경만 승인할 수 있습니다. 이 항목은 거절하세요"))
        workflow_id, step_id, base = row.workflow_id, row.step_id, row.base_version
    draft = None
    if decision == APPROVED:
        spec = scenarios.workflow(workflow_id)
        if spec.version != base:
            raise ValueError(tr(
                f"the workflow changed since the replay (v{base} → v{spec.version}): "
                "replay again",
                f"재생 이후 워크플로가 바뀌었습니다(v{base} → v{spec.version}). 다시 재생하세요"))
        draft = workflow_store.save_draft(
            _with_tier(spec, step_id, "fast").model_dump(), by,
            note=f"replay #{rec_id}: {step_id} → fast", workflow_id=workflow_id)["version"]
    elif decision != REJECTED:
        raise ValueError(f"decision must be {APPROVED} or {REJECTED}")
    with get_session() as s:
        row = s.get(Recommendation, rec_id)
        assert row is not None
        row.status, row.decided_by, row.decided_at = decision, by, datetime.now(UTC)
        row.draft_version = draft
        return _row(row)


def _row(r: Recommendation) -> dict[str, Any]:
    return {"id": r.id, "workflow_id": r.workflow_id, "step_id": r.step_id,
            "base_version": r.base_version, "verdict": r.verdict, "status": r.status,
            "report": r.report, "created_by": r.created_by,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "decided_by": r.decided_by,
            "decided_at": r.decided_at.isoformat() if r.decided_at else None,
            "draft_version": r.draft_version}
