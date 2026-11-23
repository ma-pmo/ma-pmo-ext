"""Commitment evaluation: are missed obligations noticed, and kept ones left alone?

    ma-pmo eval --commitments

The criteria were fixed before the first run (docs/COMMITMENTS-EVAL.md); each is a count that
must be zero. Cases:

- conditions: the demo portfolio as of 2026-02-16, where PROJ-14 and PROJ-31 pass G3 on
  condition. A person approves each gate with a condition of their own, so each gate gives a gate
  condition (discharged by the tracker once the blocked tasks' predecessors are done) and an
  approval condition (discharged by a person). Due in 3, 7 and 14 days.
- questions: PROJ-22 without a start date, so A2 asks; answers due in 1, 3 and 5 days. A control
  keeps the start date: no question should come.
- stakeholders: on time (the day before the due date), late (two days after) or absent.

Days pass one at a time: the stakeholder acts on their day, the tracker is checked, and the
due-date sweep runs. Every case runs in a throwaway workspace without an LLM.
"""
from __future__ import annotations

import copy
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select

from ma_pmo.agents import registry
from ma_pmo.agents.planning import PlanningAgent
from ma_pmo.core import commitments, decisions, hitl, llm, questions, runs, scenarios
from ma_pmo.core.config import get_settings
from ma_pmo.core.scope import DEFAULT_SCOPE
from ma_pmo.core.workflow import WorkflowSpec
from ma_pmo.db.models import AgentMessageRow, Communication
from ma_pmo.db.session import get_session

START = datetime(2026, 2, 16)
BEHAVIOURS = ("on_time", "late", "absent")
CONDITION_DUE = (3, 7, 14)
QUESTION_DUE = (1, 3, 5)
PERSON, OWNER = "sponsor", "owner"
CRITERIA = {  # name -> (what counts), each must be 0; fixed before the first run
    "missed_unnoticed": "missed, and never violated or its debtor never told",
    "kept_marked_missed": "kept on time, but marked violated",
    "missed_not_escalated": "missed, and not escalated to the accountable in two steps' time",
    "missed_not_reopened": "missed condition, and its decision not reopened in three steps' time",
    "needless_questions": "questions about a fact that was present",
    "unmarked_defaults": "defaults used without the output marked unconfirmed",
}
_TEXT = {"en": "commitment evaluation", "ko": "약속 평가"}
_QUESTION_SPEC = WorkflowSpec.model_validate({
    "id": "commitments_eval", "title": _TEXT, "goal": _TEXT, "description": _TEXT,
    "review": False, "steps": [{"id": "A2", "agent": "A2"}, {"id": "A5", "agent": "A5",
                                                             "needs": ["A2"]}]})


def _act_day(behaviour: str, due: int) -> int | None:
    return {"on_time": max(due - 1, 0), "late": due + 2}.get(behaviour)


@contextmanager
def _setting(**values: Any) -> Iterator[None]:
    settings = get_settings()
    saved = {k: getattr(settings, k) for k in values}
    for k, v in values.items():
        setattr(settings, k, v)
    try:
        yield
    finally:
        for k, v in saved.items():
            setattr(settings, k, v)


@contextmanager
def _offline() -> Iterator[None]:
    def down(**kw: Any) -> Any:
        raise RuntimeError("the commitment evaluation runs the deterministic path")

    saved = llm.litellm.completion
    llm.litellm.completion = down
    try:
        yield
    finally:
        llm.litellm.completion = saved


class _Tracker:
    """The demo tracker, where the blocked tasks' predecessors are done once `unblocked`."""

    def __init__(self) -> None:
        from ma_pmo.integrations.registry import get_tracker

        self.real, self.unblocked = get_tracker(), False

    def get_portfolio_status(self, scope: str) -> dict:
        status = copy.deepcopy(self.real.get_portfolio_status(scope))
        if self.unblocked:
            for p in status.get("projects", []):
                waited = {d for t in p.get("tasks", []) for d in t.get("deps", [])}
                for t in p.get("tasks", []):
                    if t["task_id"] in waited:
                        t["percent_complete"] = 100
        return status


def _told(cid: str) -> bool:
    """A notification attempt about this commitment's violation is in the communication log."""
    with get_session() as s:  # a throwaway workspace: few enough messages to scan
        ids = [m.message_id for m in s.scalars(select(AgentMessageRow))
               if (m.payload or {}).get("schema") == "commitment.v1"
               and ((m.payload or {}).get("data") or {}).get("commitment_id") == cid]
        return bool(ids) and bool(s.scalars(select(Communication).where(
            Communication.message_id.in_(ids),
            Communication.event == "commitment.violated")).first())


def _judge(c: dict, kept: bool, due_day: int, act_day: int | None,
           reopen_expected: bool) -> dict[str, Any]:
    escalate_days = get_settings().commitment_escalate_days
    steps = [h.get("step") for h in c["history"] if h["op"] == "escalate"]
    violated = any(h["op"] == "violate" for h in c["history"])
    row = {"kind": c["kind"], "kept": kept, "state": c["state"], "steps": len(steps)}
    if kept:
        row["kept_marked_missed"] = violated
        # the simulated day it was done (history keeps the wall clock)
        row["days_to_resolve"] = act_day if c["state"] == commitments.SATISFIED else None
        return row
    row["missed_unnoticed"] = not violated or "debtor" not in steps or not _told(c["id"])
    row["missed_not_escalated"] = "accountable" not in steps
    if reopen_expected:
        record = decisions.get(c["source_decision"]) if c["source_decision"] else None
        back = any(p.get("reopened", {}) and p["reopened"]["commitment"] == c["id"]
                   for p in hitl.list_pending())
        row["missed_not_reopened"] = not (record and record["status"] == "reopened" and back)
    # violated by the sweep the day after the due date; the accountable is told one step later
    row["days_to_resolve"] = due_day + 1 + escalate_days if violated else None
    return row


def condition_case(behaviour: str, due: int) -> list[dict[str, Any]]:
    """Both conditional gates approved with a condition; the stakeholder acts per `behaviour`."""
    from ma_pmo.core.sandbox import sandbox

    tracker, act = _Tracker(), _act_day(behaviour, due)
    out = []
    with sandbox("commitments-eval"), _offline(), \
            _setting(report_as_of=START.date().isoformat(), commitment_due_days=due):
        ours = {c["message_id"] for c in scenarios.run_scenario("go_nogo_decision")["commit"]}
        made = []
        for item in hitl.list_pending():
            data = item["payload"].get("data") or {}
            if item["message_id"] in ours and data.get("decision") == "conditional":
                done = hitl.resolve(item["approval_id"], approver=PERSON, decision="approve",
                                    rationale="evaluation", conditions=[{
                                        "text": f"recovery plan for {data['project_id']}",
                                        "due": (START + timedelta(days=due)).date().isoformat()}])
                made += done["commitments"]
        last = due + 3 * get_settings().commitment_escalate_days + 2
        for day in range(0, last + 1):
            today = START + timedelta(days=day)
            if day == act:
                tracker.unblocked = True
                for cid in made:
                    c = commitments.get(cid) or {}
                    if c.get("kind") == "approval_condition" and c["state"] in commitments.OPEN:
                        commitments.apply(cid, "discharge", by=OWNER, evidence=[
                            {"kind": "reference", "ref": f"DOC-{day}"}])
            with _setting(report_as_of=today.date().isoformat()):
                commitments.check_tracker(tracker)
                commitments.sweep(today)
        for cid in made:
            c = commitments.get(cid) or {}
            out.append(_judge(c, behaviour == "on_time", due, act, reopen_expected=True))
    return out


def question_case(behaviour: str | None, due: int) -> dict[str, Any]:
    """A2 asks for PROJ-22's start date (none when `behaviour` is None: the control)."""
    from ma_pmo.core.sandbox import sandbox
    from ma_pmo.eval.review import StandInTracker
    from ma_pmo.integrations.registry import get_tracker

    status = copy.deepcopy(get_tracker().get_portfolio_status(DEFAULT_SCOPE))
    if behaviour is not None:
        next(p for p in status["projects"] if p["project_id"] == "PROJ-22").pop(
            "planned_start", None)
    saved = registry._instances.get("A2")
    registry._instances["A2"] = PlanningAgent(StandInTracker(status))
    try:
        with sandbox("commitments-eval"), _offline(), \
                _setting(report_as_of=START.date().isoformat(), question_due_days=due):
            trace = scenarios.run_spec(_QUESTION_SPEC)
            asked = questions.list_open(trace["run_id"])
            row: dict[str, Any] = {"behaviour": behaviour or "control", "due": due,
                                   "asked": len(asked)}
            if behaviour is None:
                row["needless_questions"] = len(asked)
                return row
            act = _act_day(behaviour, due)
            for day in range(0, due + 4):
                today = START + timedelta(days=day)
                if day == act and asked:
                    try:
                        questions.answer(asked[0]["id"], "2026-01-12", by=OWNER)
                    except ValueError:
                        row["late_answer_refused"] = True
                with _setting(report_as_of=today.date().isoformat()):
                    commitments.sweep(today)
            plan = next((o for step in runs.finished_steps(trace["run_id"]).values()
                         for o in step.get("outputs", []) if o["schema"] == "schedule.v1"
                         and o["data"]["project_id"] == "PROJ-22"), None)
            defaulted = plan is not None and plan["data"]["tasks"][0]["early_start"] == \
                START.date().isoformat()
            row.update(run=(runs.get_run(trace["run_id"]) or {}).get("status"),
                       default_used=defaulted,
                       # an answer on time must be used, not replaced by the default
                       kept_marked_missed=behaviour == "on_time" and defaulted,
                       unmarked_defaults=int(bool(defaulted and plan is not None
                                                  and not plan.get("unconfirmed"))))
            return row
    finally:
        if saved is not None:
            registry._instances["A2"] = saved
        else:
            registry._instances.pop("A2", None)


def evaluate() -> dict[str, Any]:
    conditions = [{"behaviour": b, "due": d, **r}
                  for b in BEHAVIOURS for d in CONDITION_DUE for r in condition_case(b, d)]
    asked = [question_case(b, d) for b in BEHAVIOURS for d in QUESTION_DUE]
    controls = [question_case(None, d) for d in QUESTION_DUE]
    counts = {name: sum(int(bool(r.get(name))) for r in conditions + asked + controls)
              for name in CRITERIA}
    counts["needless_questions"] = sum(r["needless_questions"] for r in controls)
    missed = [r for r in conditions if not r["kept"]]
    kept = [r for r in conditions if r["kept"]]
    return {
        "criteria": {k: {"what": CRITERIA[k], "count": v, "pass": v == 0}
                     for k, v in counts.items()},
        "conditions": conditions, "questions": asked + controls,
        "summary": {
            "commitments": len(conditions), "kept": len(kept), "missed": len(missed),
            "questions": sum(r["asked"] for r in asked + controls),
            "escalation_messages": sum(r["steps"] for r in conditions),
            "days_to_resolve_kept": _mean([r["days_to_resolve"] for r in kept]),
            "days_to_resolve_missed": _mean([r["days_to_resolve"] for r in missed]),
            "defaults_used": sum(int(r.get("default_used", False)) for r in asked),
            "late_answers_refused": sum(int(r.get("late_answer_refused", False))
                                        for r in asked),
        },
    }


def _mean(values: list[Any]) -> float | None:
    found = [v for v in values if v is not None]
    return round(sum(found) / len(found), 1) if found else None


def to_markdown(result: dict[str, Any]) -> str:
    lines = ["# Commitment evaluation (roadmap 9)", "", "| criterion | count | target | |",
             "|---|---:|---:|---|"]
    for c in result["criteria"].values():
        lines.append(f"| {c['what']} | {c['count']} | 0 | {'pass' if c['pass'] else 'FAIL'} |")
    s = result["summary"]
    lines += ["", f"{s['commitments']} commitments ({s['kept']} kept on time, {s['missed']} "
              f"missed), {s['questions']} questions asked, {s['escalation_messages']} escalation "
              f"messages, {s['defaults_used']} defaults used, {s['late_answers_refused']} late "
              "answers refused.",
              f"Days to resolve: kept {s['days_to_resolve_kept']}, missed (until the "
              f"accountable is told) {s['days_to_resolve_missed']}.", ""]
    return "\n".join(lines)
