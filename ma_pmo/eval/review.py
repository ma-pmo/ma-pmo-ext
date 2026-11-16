"""Review ablation: what each part of the review stack adds, on labelled conflict cases.

    ma-pmo eval --review

Each case is the demo portfolio plus one project, PROJ-X, made from PROJ-22 (green, SPI 0.85,
slack 7 days, staffed) and changed so that, by construction, a gate decision or the report
contradicts another agent, or (controls) does not. Labels come from the construction and the
PMO rules it follows: a red status or a planned finish after the deadline is a high risk, a skill
nobody has or more work than a skill can take is unstaffed, a plan past the deadline week is late,
and a medium-or-higher risk belongs in the report. They are checked against what the agents
actually produced, so a case that does not show its conflict is reported, not counted.

The real A3, A4, A6, A5 (and A8) run on their deterministic path, without an LLM, in a throwaway
workspace. Conditions are cumulative, like the review teardown of ArcticSwarm (Yoon et al., 2026,
arXiv:2609.01870, Table 3):

| condition | what is on |
|---|---|
| main | nothing: every step isolated |
| +builder | A6 and A5 read their upstream and review their own output |
| +auditor | an A8 step reviews every decision |
| +commit gate | decisions commit only when reviews hold; the rest go to a person |
| +alternatives | A8 offers alternatives for challenged decisions |

Measured per case and condition: whether a gate conflict reached a person with both sides in view
(held and linked), whether a conflicting gate was committed with nobody asked (wrong commit),
whether a report conflict was fixed, whether a control was held (false hold), the approvals the
review added, LLM calls and run time. Rates carry 95% bootstrap intervals over cases.
"""
from __future__ import annotations

import contextlib
import copy
import random
import statistics
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import func, select

from ma_pmo.agents import registry
from ma_pmo.agents.cross_checks import _iso_week
from ma_pmo.core import commit, executor, hitl, llm, runs
from ma_pmo.core.config import get_settings
from ma_pmo.core.sandbox import sandbox
from ma_pmo.core.scope import DEFAULT_SCOPE
from ma_pmo.core.workflow import WorkflowSpec
from ma_pmo.db.models import AgentMessageRow, Approval, LlmCall, Project
from ma_pmo.db.session import get_session
from ma_pmo.integrations.registry import get_tracker

SCOPE = DEFAULT_SCOPE  # the demo portfolio
RISK, STAFFED, LATE = "gate.no_open_high_risk", "gate.staffed", "gate.allocation_by_deadline"
CONDITIONS = ("main", "+builder", "+auditor", "+commit gate", "+alternatives")
RESAMPLES, SEED = 2000, 7
PROJ_22_DEADLINE = "2026-03-20"
_TEXT = {"en": "x", "ko": "x"}
_STEPS: list[dict[str, Any]] = [
    {"id": "A3", "agent": "A3"},
    {"id": "A4", "agent": "A4", "needs": []},
    {"id": "A6", "agent": "A6", "needs": ["A3", "A4"], "params": {"gate": "G3-execution"}},
    {"id": "A5", "agent": "A5", "needs": ["A6"]},
]


@dataclass
class Case:
    name: str
    change: dict[str, Any]
    gate: set[str] = field(default_factory=set)  # gate constraints in conflict on PROJ-X
    report: bool = False  # A4 rates PROJ-X medium+ but the report leaves it out

    @property
    def control(self) -> bool:
        return not self.gate and not self.report


def _scaled(factor: float):
    return lambda tasks: [{**t, "effort": t["effort"] * factor} for t in tasks]


def _stalled(pct: float):
    return lambda tasks: [{**tasks[0], "percent_complete": 100.0},
                          {**tasks[1], "percent_complete": pct}]


def _late(days: int, base: str = "2026-03-13") -> dict:
    from datetime import date, timedelta

    finish = date.fromisoformat(base)
    return {"planned_finish": str(finish), "deadline": str(finish - timedelta(days=days))}


def _due(deadline: str) -> dict:  # a deadline with the planned finish a week before it
    from datetime import date, timedelta

    return {"deadline": deadline, "planned_finish": str(date.fromisoformat(deadline)
                                                        - timedelta(days=7))}


def cases() -> list[Case]:
    """35 cases: 23 with a conflict, 12 controls."""
    green = {"status": "green"}
    return [
        # a high risk under a passing gate
        *[Case(f"red_slack_{d}", {"status": "red", **_due(f"2026-03-{13 + d:02d}")}, {RISK})
          for d in (3, 7, 10)],
        *[Case(f"late_green_{d}", {**green, **_late(d)}, {RISK}, report=True)
          for d in (3, 10, 20)],
        *[Case(f"late_amber_{d}", {"status": "amber", **_late(d)}, {RISK}) for d in (5, 15)],
        # work nobody can take
        *[Case(f"no_skill_{s}", {**green, "skill": s}, {STAFFED}) for s in ("ml", "design", "ops")],
        *[Case(f"too_big_x{f}", {**green, "tasks": _scaled(f)}, {STAFFED, LATE})
          for f in (100, 200, 400)],
        # a plan that ends after the deadline
        *[Case(f"late_plan_x20_{d}", {**green, **_due(d), "tasks": _scaled(20)}, {LATE})
          for d in ("2026-01-30", "2026-02-06", "2026-02-20")],
        Case("late_plan_x10", {**green, **_due("2026-01-30"), "tasks": _scaled(10)}, {LATE}),
        # both
        *[Case(f"red_no_skill_{s}", {"status": "red", "skill": s}, {RISK, STAFFED})
          for s in ("ml", "ops")],
        # a risk the report leaves out (the gate fails on its own: SPI below 0.8)
        *[Case(f"stalled_green_{p}", {**green, "tasks": _stalled(p)}, report=True)
          for p in (40, 30, 20)],
        # controls
        *[Case(f"healthy_slack_{d}", {**green, **_late(-d)}) for d in (7, 14, 30)],
        Case("done", {**green, "percent_complete": 100.0,
                      "tasks": lambda ts: [{**t, "percent_complete": 100.0} for t in ts]}),
        *[Case(f"effort_x{f}", {**green, "tasks": _scaled(f)}) for f in (0.5, 2)],
        *[Case(f"amber_{d}", {"status": "amber", **_late(-d)}) for d in (7, 14)],
        *[Case(f"skill_{s}", {**green, "skill": s}) for s in ("backend", "data")],
        *[Case(f"far_deadline_x{f}", {**green, **_due("2026-06-30"), "tasks": _scaled(f)})
          for f in (10, 15)],
    ]


class StandInTracker:
    """A tracker that answers with a fixed portfolio status."""

    def __init__(self, status: dict) -> None:
        self.status = status

    def get_portfolio_status(self, portfolio_id: str) -> dict:
        return copy.deepcopy(self.status)


def with_project_x(base: dict, tasks: Any = None, **change: Any) -> dict:
    """`base` plus PROJ-X: a copy of PROJ-22 (green, SPI 0.85, slack 7 days) with `change`."""
    status = copy.deepcopy(base)
    x = copy.deepcopy(next(p for p in status["projects"] if p["project_id"] == "PROJ-22"))
    x.update({"project_id": "PROJ-X", "percent_complete": 85.0, **change})
    x["tasks"] = [{**t, "task_id": "X-" + t["task_id"],
                   "deps": ["X-" + d for d in t.get("deps", [])]}
                  for t in (tasks(x["tasks"]) if tasks else x["tasks"])]
    status["projects"].append(x)
    return status


def portfolio(case: Case) -> dict:
    """The demo portfolio with PROJ-X as the case describes it."""
    change = dict(case.change)
    tasks = change.pop("tasks", None)
    return with_project_x(get_tracker().get_portfolio_status(SCOPE), tasks, **change)


def workflow(condition: str) -> WorkflowSpec:
    steps = copy.deepcopy(_STEPS)
    if condition != "main":
        for s in steps:
            if s["agent"] in ("A5", "A6"):
                s["reads"] = "upstream"
    if condition == "+auditor":
        steps.append({"id": "review", "agent": "A8", "needs": ["A5"], "reads": "board"})
    return WorkflowSpec.model_validate({
        "id": "review_eval", "title": _TEXT, "goal": _TEXT, "description": _TEXT, "steps": steps,
        "review": condition in ("+commit gate", "+alternatives")}).with_review()


@contextlib.contextmanager
def stand_in(status: dict, alternatives: bool | None = None) -> Iterator[None]:
    """Real A3, A4, A5, A6 and A8 reading `status`, no LLM, alternatives on or off (None: as
    configured); everything is restored afterwards."""
    from ma_pmo.agents.auditor import AuditorAgent
    from ma_pmo.agents.governance import GovernanceAgent
    from ma_pmo.agents.reporting import ReportingAgent
    from ma_pmo.agents.resource import ResourceAgent
    from ma_pmo.agents.risk import RiskAgent

    def down(**kw: Any) -> Any:
        raise RuntimeError("the review evaluation runs the deterministic path")

    tracker = StandInTracker(status)
    settings = get_settings()
    saved = (dict(registry._instances), llm.litellm.completion, settings.review_alternatives)
    registry._instances.update({
        "A3": ResourceAgent(tracker), "A4": RiskAgent(tracker), "A5": ReportingAgent(tracker),
        "A6": GovernanceAgent(tracker), "A8": AuditorAgent(tracker)})
    llm.litellm.completion = down
    if alternatives is not None:
        settings.review_alternatives = alternatives
    try:
        yield
    finally:
        registry._instances.clear()
        registry._instances.update(saved[0])
        llm.litellm.completion = saved[1]
        settings.review_alternatives = saved[2]


def run_with(status: dict, spec: WorkflowSpec, *, alternatives: bool | None = None,
             gate: bool = False, inspect: Any = None) -> dict[str, Any]:
    """Run `spec` (reviewed if it says so) on `status` in a throwaway workspace.

    Returns the outputs, the commit gate's outcome (for a reviewed run, or any run with `gate`),
    the approval queue after the run, the run time, and what `inspect()` returns when it is
    called inside the workspace, before it is erased.
    """
    spec = spec.with_review()
    with stand_in(status, alternatives), sandbox("review-eval"):
        x = next(p for p in status["projects"] if p["project_id"] == "PROJ-X")
        with get_session() as s:  # risks and allocations point at a real project
            s.add(Project(id="PROJ-X", portfolio_id=SCOPE, skill=x["skill"], status=x["status"],
                          deadline=x.get("deadline")))
        started = time.perf_counter()
        with runs.track("scenario", spec.id, SCOPE, state={"spec": spec.model_dump()}) as rid:
            outputs = executor.execute(rid, spec, SCOPE, "evaluate").outputs
            decided = commit.check(rid, spec) if spec.review or gate else None
        elapsed = (time.perf_counter() - started) * 1000
        return {"run_id": rid, "outputs": outputs, "commit": decided,
                "pending": hitl.list_pending(), "spec": spec, "ms": elapsed,
                "inspected": inspect() if inspect else None}


def _counts() -> tuple[int, int]:
    """LLM calls made, and approvals the review created (not those it only annotated)."""
    with get_session() as s:
        calls = s.scalar(select(func.count()).select_from(LlmCall)) or 0
        added = s.scalar(select(func.count()).select_from(Approval).join(
            AgentMessageRow, AgentMessageRow.message_id == Approval.message_id).where(
            Approval.reason.is_not(None), AgentMessageRow.human_gate_required.is_(False),
            AgentMessageRow.confidence >= get_settings().hitl_confidence_threshold)) or 0
    return calls, added


def run_case(case: Case, condition: str) -> dict[str, Any]:
    """One case under one condition: what the agents found, and what reached a person."""
    result = run_with(portfolio(case), workflow(condition),
                      alternatives=condition == "+alternatives", inspect=_counts)
    calls, added = result["inspected"]
    return _measure(case, result["outputs"], result["commit"] or [], result["pending"], calls,
                    added, result["ms"])


def _measure(case: Case, outputs: list[dict], decided: list[dict], pending: list[dict],
             calls: int, added: int, elapsed: float) -> dict[str, Any]:
    gate = next(o["data"] for o in outputs
                if o["schema"] == "gate_review.v1" and o["data"]["project_id"] == "PROJ-X")
    alert = next((o["data"]["severity"] for o in outputs if o["schema"] == "risk_alert.v1"
                  and o["data"]["project_id"] == "PROJ-X"), None)
    alloc = next(o["data"] for o in outputs if o["schema"] == "allocation.v1")
    report = next(o["data"] for o in outputs if o["schema"] == "report.v1")
    in_report = "PROJ-X" in " ".join(report.get("key_risks", []))
    # the conflicts in what the agents produced, by the labelling rules (not by the reviewers);
    # the report gap is only visible where A5 does not fix it, i.e. under "main"
    found: set[str] = set()
    if gate["decision"] == "pass":
        if alert in ("high", "critical"):
            found.add(RISK)
        if any(u["project_id"] == "PROJ-X" for u in alloc.get("unstaffed", [])):
            found.add(STAFFED)
        weeks = [ln["week"] for ln in alloc["plan"] if ln["project_id"] == "PROJ-X"]
        due = _iso_week(case.change.get("deadline") or PROJ_22_DEADLINE)
        if due and weeks and max(weeks) > due:
            found.add(LATE)
    report_gap = alert in ("medium", "high", "critical") and not in_report
    gate_post = next((d for d in decided if d["schema"] == "gate_review.v1"
                      and d["project_id"] == "PROJ-X"), None)
    item = next((p for p in pending
                 if gate_post is not None and p["message_id"] == gate_post["message_id"]), None)
    review = (item or {}).get("review") or {}
    challenged = {c["constraint"] for c in review.get("challenges", [])}
    held = gate_post is not None and gate_post["status"] == commit.REVIEW_PENDING
    linked = held and bool(case.gate) and case.gate <= challenged
    return {
        "case": case.name, "control": case.control, "gate_conflicts": len(case.gate),
        "label_ok": found == case.gate and report_gap == case.report,
        "surfaced": len(case.gate) if linked else 0,
        "wrong_commit": bool(case.gate) and not held and gate["decision"] == "pass",
        "report_fixed": case.report and in_report,
        "false_hold": case.control and held,
        "alternatives": len(review.get("alternatives", [])),
        "added_approvals": added, "llm_calls": calls, "ms": round(elapsed, 1),
    }


def _ci(values: list[float]) -> tuple[float, float, float]:
    """Mean with a 95% bootstrap interval."""
    if not values:
        return 0.0, 0.0, 0.0
    rng = random.Random(SEED)
    means = sorted(statistics.fmean(rng.choices(values, k=len(values)))
                   for _ in range(RESAMPLES))
    return (statistics.fmean(values), means[int(0.025 * RESAMPLES)],
            means[int(0.975 * RESAMPLES) - 1])


def evaluate(conditions: tuple[str, ...] = CONDITIONS,
             selected: list[Case] | None = None) -> dict[str, Any]:
    """Every case under every condition, with rates and intervals per condition."""
    chosen = selected if selected is not None else cases()
    rows = {c: [run_case(case, c) for case in chosen] for c in conditions}
    summary = {}
    for condition, results in rows.items():
        conflicts = [r for r in results if r["gate_conflicts"]]
        reports = [r for r, case in zip(results, chosen, strict=True) if case.report]
        controls = [r for r in results if r["control"]]
        per_conflict = [1.0] * sum(r["surfaced"] for r in conflicts) + [0.0] * (
            sum(r["gate_conflicts"] for r in conflicts) - sum(r["surfaced"] for r in conflicts))
        summary[condition] = {
            "surfaced": _ci(per_conflict),
            "wrong_commit": _ci([float(r["wrong_commit"]) for r in conflicts]),
            "report_fixed": _ci([float(r["report_fixed"]) for r in reports]),
            "false_hold": _ci([float(r["false_hold"]) for r in controls]),
            "added_approvals": statistics.fmean(r["added_approvals"] for r in results),
            "alternatives": statistics.fmean(r["alternatives"] for r in conflicts) if conflicts
            else 0.0,
            "llm_calls": sum(r["llm_calls"] for r in results),
            "ms": statistics.median(r["ms"] for r in results),
        }
    return {"cases": len(chosen), "conflicts": sum(1 for c in chosen if not c.control),
            "gate_conflicts": sum(len(c.gate) for c in chosen),
            "report_conflicts": sum(c.report for c in chosen),
            "controls": sum(c.control for c in chosen),
            # labels are checked where nothing fixes or hides a conflict
            "labels_ok": all(r["label_ok"] for r in rows["main"]) if "main" in rows else None,
            "mislabelled": [r["case"] for r in rows.get("main", []) if not r["label_ok"]],
            "summary": summary, "rows": rows}


def demo_workload() -> list[dict[str, Any]]:
    """Every built-in scenario on the demo data with review on: what it would ask of people.

    Per scenario: decisions held for review, of which newly queued (not already asked for by the
    decision itself) and annotated (already queued, now with the review attached), with the
    challenged constraints, and the run time with review against without.
    """
    from ma_pmo.core import scenarios

    def down(**kw: Any) -> Any:
        raise RuntimeError("the review evaluation runs the deterministic path")

    saved = llm.litellm.completion
    llm.litellm.completion = down
    out = []
    try:
        for sid in sorted(scenarios.SCENARIOS):
            spec = scenarios.loaded(sid)
            timing = {}
            for reviewed in (False, True):
                with sandbox("review-eval"):
                    started = time.perf_counter()
                    trace = scenarios.run_spec(spec.model_copy(update={"review": reviewed}))
                    timing[reviewed] = (time.perf_counter() - started) * 1000
                    if not reviewed:
                        continue
                    held = [c for c in trace["commit"] or []
                            if c["status"] == commit.REVIEW_PENDING]
                    queued = {p["message_id"]: p for p in hitl.list_pending()}
                    with get_session() as s:
                        gated = set(s.scalars(select(AgentMessageRow.message_id).where(
                            AgentMessageRow.human_gate_required.is_(True))))
                    new = [c for c in held if c["message_id"] not in gated]
                    reasons = sorted({ch["constraint"] for c in held
                                      for ch in queued.get(c["message_id"], {}).get(
                                          "review", {}).get("challenges", [])}
                                     | {m for c in held for m in c["missing"]})
                    out.append({"scenario": sid, "decisions": len(trace["commit"] or []),
                                "held": len(held), "new": len(new),
                                "annotated": len(held) - len(new),
                                "new_items": [f"{c['project_id'] or c['schema']}" for c in new],
                                "why": reasons})
            out[-1]["ms_off"], out[-1]["ms_on"] = round(timing[False], 1), round(timing[True], 1)
    finally:
        llm.litellm.completion = saved
    return out


def _pct(ci: tuple[float, float, float]) -> str:
    mean, low, high = (round(v * 100) for v in ci)
    return f"{mean}% [{low}, {high}]"


def to_markdown(result: dict[str, Any], workload: list[dict[str, Any]] | None = None) -> str:
    """The ablation, and the demo workload if given, as Markdown tables (English)."""
    lines = [
        f"{result['cases']} cases: {result['conflicts']} with a conflict "
        f"({result['gate_conflicts']} gate conflicts, {result['report_conflicts']} report "
        f"conflicts), {result['controls']} controls. Labels match what the agents produced: "
        f"{'yes' if result['labels_ok'] else 'no ' + ', '.join(result['mislabelled'])}.",
        "",
        "| Condition | Gate conflicts that reached a person | Conflicting gates committed "
        "| Report conflicts fixed | Controls held | Approvals added per run | Alternatives per "
        "conflict | LLM calls | Median run (ms) |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for condition, s in result["summary"].items():
        lines.append(f"| {condition} | {_pct(s['surfaced'])} | {_pct(s['wrong_commit'])} | "
                     f"{_pct(s['report_fixed'])} | {_pct(s['false_hold'])} | "
                     f"{s['added_approvals']:.2f} | {s['alternatives']:.1f} | {s['llm_calls']} | "
                     f"{s['ms']:.0f} |")
    if workload:
        lines += ["", "| Scenario | Decisions | Held | Newly queued | Already queued | Why | "
                  "Run ms (off → on) |", "|---|---|---|---|---|---|---|"]
        for w in workload:
            lines.append(f"| {w['scenario']} | {w['decisions']} | {w['held']} | {w['new']} | "
                         f"{w['annotated']} | {', '.join(w['why']) or '–'} | "
                         f"{w['ms_off']:.0f} → {w['ms_on']:.0f} |")
        lines.append(f"| **all** | {sum(w['decisions'] for w in workload)} | "
                     f"{sum(w['held'] for w in workload)} | {sum(w['new'] for w in workload)} | "
                     f"{sum(w['annotated'] for w in workload)} | | |")
    return "\n".join(lines)
