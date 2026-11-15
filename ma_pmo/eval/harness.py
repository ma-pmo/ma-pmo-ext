"""Empirical harness for hypotheses H1–H5 (§9) — kpi_event aggregation + ground-truth comparison.

Fills KPIs with the deterministic agents (A2, A3, A6) and rule-based risk detection, then
computes metrics against baselines/ground truth. Mostly runs without an API key.
"""
from __future__ import annotations

import json
import statistics
from pathlib import Path

from sqlalchemy import select

from ma_pmo.agents.governance import GovernanceAgent
from ma_pmo.agents.knowledge import KnowledgeAgent
from ma_pmo.agents.planning import PlanningAgent
from ma_pmo.agents.resource import ResourceAgent
from ma_pmo.agents.risk_signals import baseline_severity, compute_signals
from ma_pmo.core.i18n import tr
from ma_pmo.core.scope import DEFAULT_SCOPE
from ma_pmo.eval.aggregate import metric_summary
from ma_pmo.integrations.registry import get_tracker

_FIX = Path(__file__).resolve().parent.parent / "fixtures"
_POSITIVE = {"medium", "high", "critical"}


def _load(name: str) -> dict:
    return json.loads((_FIX / name).read_text(encoding="utf-8"))


def populate_deterministic_kpis(scope: str = DEFAULT_SCOPE) -> None:
    """Run the deterministic agents to fill KPIs (delivery, resource, gate)."""
    PlanningAgent().run({"task_ref": scope})
    ResourceAgent().run({"task_ref": scope})
    GovernanceAgent().run({"task_ref": scope, "gate": "G2-planning"})


# ── H1: shorter report cycle time ───────────────────────────────
def h1_report_time(baselines: dict | None = None) -> dict:
    base = (baselines or _load("baselines.json"))["manual_report_cycle_time_sec"]
    rct = metric_summary("report_cycle_time_sec")
    auto = rct["avg"]
    reduction = None if auto is None else round((1 - auto / base) * 100, 1)
    return {
        "hypothesis": tr("H1 shorter reporting time", "H1 보고시간 단축"),
        "baseline_manual_sec": base,
        "automated_avg_sec": auto,
        "reduction_pct": reduction,
        "n": rct["count"],
        "note": None if auto else tr(
            "No RCT data — run A5 (LLM) first", "RCT 데이터 없음 — A5(LLM) 실행 필요"
        ),
    }


# ── H2: lower resource idle rate ────────────────────────────────
def h2_idle_rate(baselines: dict | None = None) -> dict:
    target = (baselines or _load("baselines.json"))["target_utilization_pct"]
    util = metric_summary("utilization_pct")
    idle = metric_summary("idle_pct")
    return {
        "hypothesis": tr("H2 idle rate", "H2 유휴율"),
        "utilization_avg_pct": util["avg"],
        "idle_avg_pct": idle["avg"],
        "target_utilization_pct": target,
        "meets_target": None if util["avg"] is None else util["avg"] >= target,
        "n": util["count"],
    }


# ── H3: risk detection performance (rule-based vs. ground truth) ─
def h3_risk_detection(scope: str = DEFAULT_SCOPE, labels: dict | None = None) -> dict:
    labels = labels if labels is not None else _load("risk_ground_truth.json")["labels"]
    status = get_tracker().get_portfolio_status(scope)
    tp = fp = fn = tn = 0
    rows = []
    for proj in status.get("projects", []):
        pid = proj["project_id"]
        pred = baseline_severity(compute_signals(proj))
        actual = labels.get(pid, "low")
        pred_pos, actual_pos = pred in _POSITIVE, actual in _POSITIVE
        tp += pred_pos and actual_pos
        fp += pred_pos and not actual_pos
        fn += not pred_pos and actual_pos
        tn += not pred_pos and not actual_pos
        rows.append({"project_id": pid, "predicted": pred, "actual": actual})

    precision = tp / (tp + fp) if (tp + fp) else None
    recall = tp / (tp + fn) if (tp + fn) else None
    f1 = (
        2 * precision * recall / (precision + recall)
        if precision and recall
        else (0.0 if precision is not None and recall is not None else None)
    )
    return {
        "hypothesis": tr(
            "H3 risk/schedule (rule-based baseline)", "H3 리스크/일정 (규칙기반 baseline)"
        ),
        "confusion": {"tp": tp, "fp": fp, "fn": fn, "tn": tn},
        "precision": round(precision, 3) if precision is not None else None,
        "recall": round(recall, 3) if recall is not None else None,
        "f1": round(f1, 3) if f1 is not None else None,
        "detail": rows,
    }


# ── H4: knowledge (A7) — do other agents' decisions rest on its lessons? ─────────────────
def _lessons_used() -> dict:
    """Runs with A7, and messages of other agents that cite one of its answers as evidence.

    Counting A7's own answers would show only that A7 ran; what H4 claims is that the lessons
    reach decisions, so this counts the other agents' messages that rest on them.
    """
    from ma_pmo.db.models import AgentMessageRow
    from ma_pmo.db.session import get_session

    with get_session() as s:
        rows = s.scalars(select(AgentMessageRow)).all()
        answers = {r.message_id: r.run_id for r in rows if r.sender == "A7"}
        citing = [r for r in rows if r.sender != "A7" and any(
            e.get("kind") == "message" and e.get("ref") in answers for e in (r.evidence or []))]
        return {"runs": len({run for run in answers.values() if run}),
                "citing": len(citing), "agents": sorted({r.sender for r in citing})}


def h4_knowledge_ablation(query: str | None = None) -> dict:
    query = query or tr("data migration delay risk", "데이터 마이그레이션 지연 리스크")
    hits = KnowledgeAgent().retrieve(query, k=3)
    top_sim = hits[0]["similarity"] if hits else 0
    used = _lessons_used()
    gain = used["citing"] if used["runs"] else None
    if gain is None:
        note = tr("No run with A7 yet — run a scenario that uses it (e.g. knowledge_kickoff)",
                  "A7이 포함된 실행이 아직 없음 — A7을 쓰는 시나리오"
                  "(예: knowledge_kickoff)를 실행하세요")
    elif gain:
        note = tr(f"{gain} messages of {', '.join(used['agents'])} cite A7's lessons "
                  f"in {used['runs']} runs; without A7 there is nothing to cite",
                  f"{used['runs']}개 실행에서 {', '.join(used['agents'])}의 메시지 {gain}건이 "
                  "A7의 교훈을 근거로 인용 — A7이 없으면 인용할 것이 없음")
    else:
        note = tr(f"A7 ran in {used['runs']} runs, but no other agent's message cites its lessons",
                  f"A7이 {used['runs']}개 실행에 있었지만 다른 에이전트의 메시지 중 "
                  "교훈을 인용한 것이 없음")
    return {
        "hypothesis": tr("H4 success rate (A7 ablation)", "H4 성공률 (A7 ablation)"),
        "a7_enabled": {"citations": len(hits), "top_similarity": top_sim,
                       "messages_citing_lessons": used["citing"]},
        "a7_disabled": {"citations": 0, "top_similarity": 0, "messages_citing_lessons": 0},
        "runs_with_a7": used["runs"],
        "citing_agents": used["agents"],
        "coverage_gain": gain,
        "note": note,
    }


# ── H5: stratification by portfolio complexity ──────────────────
def h5_complexity(scope: str = DEFAULT_SCOPE) -> dict:
    status = get_tracker().get_portfolio_status(scope)
    projs = status.get("projects", [])

    def complexity(p: dict) -> int:
        tasks = p.get("tasks", [])
        dep_edges = sum(len(t.get("deps", [])) for t in tasks)
        return len(tasks) + dep_edges

    scored = [(complexity(p), p) for p in projs]
    if not scored:
        return {"hypothesis": tr("H5 moderation", "H5 조절"), "strata": {}}
    med = statistics.median(c for c, _ in scored)

    def _spi(p):
        tasks = p.get("tasks", [])
        pv = sum(t.get("effort", 0.0) for t in tasks) or 1.0
        ev = sum(t.get("effort", 0.0) * t.get("percent_complete", 0.0) / 100 for t in tasks)
        return ev / pv

    strata: dict[str, list] = {"low": [], "high": []}
    for c, p in scored:
        strata["high" if c > med else "low"].append(_spi(p))
    return {
        "hypothesis": tr(
            "H5 moderation (complexity strata)", "H5 조절 (복잡성 층화)"
        ),
        "median_complexity": med,
        "strata": {
            k: {"n": len(v), "avg_spi": round(statistics.mean(v), 3) if v else None}
            for k, v in strata.items()
        },
        "note": _h5_note(strata),
    }


def _h5_note(strata: dict[str, list]) -> str:
    """What the strata show, not what H5 hopes they show."""
    if not strata["low"] or not strata["high"]:
        return tr("Too few projects to compare strata", "층을 비교할 프로젝트가 부족함")
    low, high = statistics.mean(strata["low"]), statistics.mean(strata["high"])
    if high < low:
        return tr(f"SPI is lower in the high-complexity stratum ({high:.3f} vs. {low:.3f}): "
                  "consistent with a moderation effect",
                  f"고복잡도 층의 SPI가 더 낮음({high:.3f} / {low:.3f}): 조절효과와 일치")
    return tr(f"SPI is not lower in the high-complexity stratum ({high:.3f} vs. {low:.3f}): "
              "no moderation effect in this data",
              f"고복잡도 층의 SPI가 낮지 않음({high:.3f} / {low:.3f}): "
              "이 데이터에서는 조절효과 없음")


def run_all(populate: bool = True, scope: str = DEFAULT_SCOPE,
            baselines: dict | None = None, labels: dict | None = None) -> dict:
    """Run H1–H5. `baselines`/`labels` override the bundled fixtures (see eval/dataset.py)."""
    from ma_pmo.eval.calibration import calibration_report

    if populate:
        populate_deterministic_kpis(scope)
    labels = labels if labels is not None else _load("risk_ground_truth.json")["labels"]
    return {
        "H1": h1_report_time(baselines),
        "H2": h2_idle_rate(baselines),
        "H3": h3_risk_detection(scope, labels),
        "H4": h4_knowledge_ablation(),
        "H5": h5_complexity(scope),
        "calibration": calibration_report(scope, labels),
    }
