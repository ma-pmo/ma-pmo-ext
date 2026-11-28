"""Record completeness: does every decision leave the record roadmap 8 promises?

    ma-pmo eval --records

Runs every built-in scenario on the demo data, and the review evaluation's labelled cases (with
review, the commit gate and alternatives on), each in a throwaway workspace on the deterministic
path (no LLM). A stand-in person then decides every approval that reached the queue: rejecting
every other one and approving the rest, first without a reason, then with one where the rule
asks for it. Two stand-in notifiers receive every event, one that accepts and one that fails, so
sent, failed and skipped attempts all occur; nobody real is told.

Measured, with a target of 100% each:

| measure | of what |
|---|---|
| agent decisions recorded | commit-gate decisions with a decision record |
| person decisions recorded | decided approvals whose record is accepted or rejected |
| reason where required | rejections and overrides of a challenged decision that keep the reason |
| refused without a reason | of those, how many were refused when first sent without one |
| traceable to a step | records whose PROV export derives them from a step's message |
| notification attempts recorded | events x notifiers, against rows in the communication log |
| traceable to evidence | records whose message or reviews cite evidence |
| cited evidence that resolves | cited messages, tracker fields, lessons and steps that exist |
"""
from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any

from sqlalchemy import func, select

from ma_pmo.core import decisions, hitl, llm, provenance, runs
from ma_pmo.core.config import get_settings
from ma_pmo.db.models import (
    AgentMessageRow,
    Approval,
    Communication,
    DecisionRecord,
    KnowledgeDoc,
    Run,
)
from ma_pmo.db.session import get_session
from ma_pmo.integrations import dispatch, registry
from ma_pmo.integrations.base import Event, EventType

PERSON = "eval-person"
TARGETS = ("agent_recorded", "person_recorded", "reason_kept", "refused", "to_step",
           "notified")


class _Accepts:
    name = "accepts"

    def send(self, event: Event) -> None:
        pass


class _Fails:
    name = "fails"

    def send(self, event: Event) -> None:
        raise ConnectionError("stand-in notifier is down")


@contextmanager
def _stand_ins(counter: list[int]) -> Iterator[None]:
    """No LLM, two stand-in notifiers, and a count of the events handed to them."""
    def down(**kw: Any) -> Any:
        raise RuntimeError("the record evaluation runs the deterministic path")

    real_emit, real_build, real_completion = dispatch.emit, dispatch.build_notifiers, \
        llm.litellm.completion

    def counting(events: Any, **kw: Any) -> list[dict]:
        """Count the events, and the attempts the log should show for them: one row per
        notifier, or one skip row per event (dry run, no notifier, not subscribed)."""
        events = list(events)
        counter[0] += len(events)
        if events:
            targets = kw.get("notifiers")
            per = len(targets) if targets is not None else 2
            wanted = dispatch.wanted_types(kw.get("settings") or get_settings())
            for event in events:
                skip = registry.is_demo_only() or per == 0 or (
                    wanted and event.type.value not in wanted
                    and event.type is not EventType.TEST)
                counter[1] += 1 if skip else per
        return real_emit(events, **kw)

    dispatch.emit = counting  # type: ignore[assignment]
    dispatch.build_notifiers = lambda settings: [_Accepts(), _Fails()]  # type: ignore[assignment,misc]
    llm.litellm.completion = down
    try:
        yield
    finally:
        dispatch.emit = real_emit  # type: ignore[assignment]
        dispatch.build_notifiers = real_build  # type: ignore[assignment]
        llm.litellm.completion = real_completion
        dispatch.reset_breakers()


@contextmanager
def _telling() -> Iterator[None]:
    """A sandbox is a dry run that tells nobody; here the stand-in notifiers must be told."""
    token = registry._demo_only.set(False)
    try:
        yield
    finally:
        registry._demo_only.reset(token)


def _decide_everything() -> dict[str, int]:
    """The stand-in person decides every pending approval."""
    out = {"decided": 0, "needed": 0, "refused": 0}
    for i, item in enumerate(hitl.list_pending()):
        decision = "reject" if i % 2 else "approve"
        challenged = bool((item.get("review") or {}).get("challenges"))
        reason = None
        if decision == "reject" or challenged:
            out["needed"] += 1
            try:
                hitl.resolve(item["approval_id"], approver=PERSON, decision=decision)
            except ValueError:
                out["refused"] += 1
            reason = f"evaluation: {decision} {item['approval_id']}"
        hitl.resolve(item["approval_id"], approver=PERSON, decision=decision, rationale=reason)
        out["decided"] += 1
    return out


def _traced(record_id: str) -> tuple[bool, bool]:
    """(derived from a message a step generated, that message or its reviews cite evidence)."""
    doc = provenance.for_decision(record_id) or {}
    dec = f"dec:{record_id}"
    derived = list(doc.get("wasDerivedFrom", {}).values())
    used = {d["prov:usedEntity"] for d in derived if d["prov:generatedEntity"] == dec}
    generated = {g["prov:entity"] for g in doc.get("wasGeneratedBy", {}).values()
                 if g["prov:activity"].startswith("step:")}
    to_step = any(u.startswith("msg:") and u in generated for u in used)
    to_evidence = any(d["prov:generatedEntity"] in used for d in derived)
    return to_step, to_evidence


def _steps(run_id: str | None) -> set[str]:
    """The step ids of a run's workflow."""
    if not run_id:
        return set()
    spec = runs.get_state(run_id).get("spec") or {}
    return {step.get("id") for step in spec.get("steps", []) if step.get("id")}


def _resolving() -> tuple[int, int]:
    """(evidence cited by any message, of it what exists): the cited message is in the log, the
    tracker field is on that project in the sender's tracker, the lesson is stored, the step is
    in the run's workflow."""
    from ma_pmo.agents import registry as agents
    from ma_pmo.integrations.registry import get_tracker

    projects: dict[str, dict[str, dict]] = {}

    def project(sender: str, scope: str, pid: str) -> dict:
        if sender not in projects:
            tracker = getattr(agents._instances.get(sender), "tracker", None) or get_tracker()
            projects[sender] = {p["project_id"]: p for p in
                                tracker.get_portfolio_status(scope).get("projects", [])}
        return projects[sender].get(pid) or {}

    cited = found = 0
    with get_session() as s:
        ids = set(s.scalars(select(AgentMessageRow.message_id)))
        lessons = set(s.scalars(select(KnowledgeDoc.id)))
        rows = [(r.sender, r.task_ref, r.run_id, r.evidence or [])
                for r in s.scalars(select(AgentMessageRow))]
    for sender, task_ref, run_id, evidence in rows:
        for ev in evidence:
            cited += 1
            kind, ref, field = ev.get("kind"), ev.get("ref"), ev.get("field")
            if kind == "message":
                found += ref in ids
            elif kind == "tracker":
                found += bool(field) and field in project(sender, task_ref.split("/")[0], ref)
            elif kind == "knowledge":
                found += ref in lessons
            elif kind == "step":
                found += ref in _steps(run_id)
    return cited, found


def measure(events: list[int]) -> dict[str, int]:
    """Counts for the workspace in use, after its runs: call inside the throwaway workspace."""
    acted = _decide_everything()
    dispatch.flush(timeout=30)
    outcome = [item for rid in _run_ids() for item in runs.get_state(rid).get("commit") or []]
    recorded = {r["message_id"] for r in decisions.list_records(limit=100_000)}
    with get_session() as s:
        people = s.scalars(select(Approval).where(Approval.decision != "pending")).all()
        person_records = {(r.approval_id, r.status) for r in s.scalars(select(DecisionRecord))}
        kept = sum(1 for a in people if a.rationale and (
            a.decision == "reject" or (a.reason or {}).get("challenges")))
        person_ok = sum(1 for a in people if (a.id, "accepted" if a.decision == "approve"
                                              else "rejected") in person_records)
        with_message = list(s.scalars(select(DecisionRecord.id).where(
            DecisionRecord.message_id.is_not(None))))
        rows = s.scalar(select(func.count()).select_from(Communication)) or 0
        by_status: dict[str, int] = {
            status: count for status, count in s.execute(
                select(Communication.status, func.count()).group_by(Communication.status))}
    traced = [_traced(r) for r in with_message]
    cited, resolved = _resolving()
    return {
        "agent_decisions": len(outcome),
        "agent_recorded": sum(1 for o in outcome if o["message_id"] in recorded),
        "person_decisions": len(people), "person_recorded": person_ok,
        "reason_needed": acted["needed"], "reason_kept": kept, "refused": acted["refused"],
        "records": len(with_message), "to_step": sum(t[0] for t in traced),
        "to_evidence": sum(t[1] for t in traced), "cited": cited, "resolved": resolved,
        "events": events[0], "attempts": events[1], "notified": rows,
        "sent": by_status.get("sent", 0), "failed": by_status.get("failed", 0),
        "skipped": by_status.get("skipped", 0),
    }


def _run_ids() -> list[str]:
    with get_session() as s:
        return list(s.scalars(select(Run.id)))


def _one(run: Callable[[Callable[[], dict]], dict]) -> dict[str, int]:
    events = [0, 0]  # events emitted, attempts they should leave in the log
    with _stand_ins(events), _telling():
        return run(lambda: measure(events))


def scenarios() -> list[dict[str, Any]]:
    """Every built-in scenario on the demo data."""
    from ma_pmo.core import scenarios as catalog
    from ma_pmo.core.sandbox import sandbox

    out = []
    for sid in sorted(catalog.SCENARIOS):
        def run(inspect: Callable[[], dict], sid: str = sid) -> dict:
            with sandbox("records-eval"), _telling():
                catalog.run_spec(catalog.loaded(sid))
                return inspect()
        out.append({"name": sid, **_one(run)})
    return out


def review_cases() -> list[dict[str, Any]]:
    """The review evaluation's labelled cases, reviewed with alternatives on."""
    from ma_pmo.eval import review

    out = []
    for case in review.cases():
        def run(inspect: Callable[[], dict], case: review.Case = case) -> dict:
            def inside() -> dict:
                with _telling():
                    return inspect()
            got = review.run_with(review.portfolio(case), review.workflow("+alternatives"),
                                  alternatives=True, inspect=inside)
            return got["inspected"]
        out.append({"name": case.name, **_one(run)})
    return out


def _sum(rows: list[dict[str, Any]]) -> dict[str, int]:
    return {k: sum(r[k] for r in rows) for k in rows[0] if k != "name"} if rows else {}


def summary(rows: list[dict[str, Any]]) -> dict[str, float | None]:
    """Each measure as a share; None when nothing was there to measure."""
    t = _sum(rows)

    def share(part: str, whole: str) -> float | None:
        return t[part] / t[whole] if t.get(whole) else None

    return {"agent_recorded": share("agent_recorded", "agent_decisions"),
            "person_recorded": share("person_recorded", "person_decisions"),
            "reason_kept": share("reason_kept", "reason_needed"),
            "refused": share("refused", "reason_needed"),
            "to_step": share("to_step", "records"),
            "notified": share("notified", "attempts"),
            "to_evidence": share("to_evidence", "records"),
            "resolved": share("resolved", "cited")}


def evaluate() -> dict[str, Any]:
    out: dict[str, Any] = {}
    for name, rows in (("scenarios", scenarios()), ("review_cases", review_cases())):
        out[name] = {"rows": rows, "total": _sum(rows), "share": summary(rows)}
    return out


def _pct(v: float | None) -> str:
    return "–" if v is None else f"{v * 100:.0f}%"


LABELS = {"agent_recorded": ("agent decisions recorded", "agent_decisions"),
          "person_recorded": ("person decisions recorded", "person_decisions"),
          "reason_kept": ("reason where required", "reason_needed"),
          "refused": ("refused without a reason", "reason_needed"),
          "to_step": ("traceable to a step", "records"),
          "notified": ("notification attempts recorded", "attempts"),
          "to_evidence": ("traceable to evidence", "records"),
          "resolved": ("cited evidence that resolves", "cited")}


def to_markdown(result: dict[str, Any]) -> str:
    lines = ["# Record completeness (roadmap 8)", ""]
    for name, title in (("scenarios", "Built-in scenarios, demo data"),
                        ("review_cases", "Review cases (+alternatives)")):
        part = result[name]
        lines += [f"## {title} ({len(part['rows'])} runs)", "",
                  "| measure | share | of |", "|---|---:|---:|"]
        for key, (label, whole) in LABELS.items():
            of = part["total"].get(whole, 0)
            lines.append(f"| {label} | {_pct(part['share'][key])} | {of} |")
        t = part["total"]
        lines += ["", f"Notification attempts: {t.get('sent', 0)} sent, {t.get('failed', 0)} "
                  f"failed, {t.get('skipped', 0)} skipped ({t.get('events', 0)} events, "
                  "2 stand-in notifiers; a run inside the review harness is a dry run, so its "
                  "events are logged as skipped).", ""]
    return "\n".join(lines)
