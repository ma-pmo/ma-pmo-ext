"""Commitments: the obligations a decision creates, with a state and a due date (roadmap 9).

A commitment is C(debtor, creditor, antecedent, consequent): the debtor owes the creditor the
consequent once the antecedent holds (Singh). It is

- created from the conditions of a conditional gate once the gate is in force (committed, or
  approved by a person), from conditions a person attaches when approving, and from an
  alternative a person adopts (roadmap 7);
- due by the date given, or `MA_PMO_COMMITMENT_DUE_DAYS` (14) after the project calendar's
  today (`MA_PMO_REPORT_AS_OF` when set, as the agents use it);
- `conditional` while its antecedent does not hold, then `active`;
- `satisfied` when discharged, by a person with a reference or by the tracker (a gate condition
  is checked against the same criterion the gate used);
- `violated` when cancelled while active, or when its due date passes; `expired` when its
  antecedent did not hold by `detach_by`; `cancelled` when cancelled while still conditional;
  `released` when its creditor lets it go (also after a violation, which ends the escalation);
- delegated (new debtor) or assigned (new creditor) without changing its state.

Every operation is also a `commitment.v1` message in the conversation of the decision it came
from, replying to that decision, so nothing changes silently.

The due-date sweep (`sweep`, run before every run, on webhooks, and by `ma-pmo commitments
sweep` from cron) violates what is overdue and walks each violation along its escalation chain,
one step every `MA_PMO_COMMITMENT_ESCALATE_DAYS`: tell the debtor, then the accountable person
(the creditor), then reopen the decision (back to the approval queue). Each step is a message and
a notification, so the communication log shows it. Sweeping again changes nothing, and a sweep
after downtime catches up.
"""
from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select

from ma_pmo.core.config import get_settings
from ma_pmo.core.i18n import tr, use_lang
from ma_pmo.core.times import iso
from ma_pmo.db.models import AgentMessageRow, Commitment
from ma_pmo.db.session import get_session

CONDITIONAL, ACTIVE, SATISFIED = "conditional", "active", "satisfied"
VIOLATED, EXPIRED, CANCELLED, RELEASED = "violated", "expired", "cancelled", "released"
OPEN = {CONDITIONAL, ACTIVE}
TRACKER = "tracker"


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _today() -> datetime:
    """The project calendar's today: `MA_PMO_REPORT_AS_OF` when set (as the agents use it)."""
    as_of = get_settings().report_as_of
    return _date(as_of) or _now() if as_of else _now()


def _date(value: str | datetime | None) -> datetime | None:
    """A date, an ISO datetime, or an ISO week like 2026-W12 (its Friday)."""
    if value is None or isinstance(value, datetime):
        return value
    week = re.fullmatch(r"(\d{4})-W(\d{2})", value)
    if week:
        return datetime.fromisocalendar(int(week[1]), int(week[2]), 5)
    return datetime.fromisoformat(value).replace(tzinfo=None)


def as_dict(row: Commitment) -> dict[str, Any]:
    return {"id": row.id, "kind": row.kind, "debtor": row.debtor, "creditor": row.creditor,
            "antecedent": row.antecedent, "consequent": row.consequent,
            "detach_by": iso(row.detach_by), "due": iso(row.due), "state": row.state,
            "project_id": row.project_id, "source_message": row.source_message,
            "source_decision": row.source_decision, "source_approval": row.source_approval,
            "conversation_id": row.conversation_id, "check": row.check,
            "evidence": row.evidence or [], "history": row.history or [],
            "violated_at": iso(row.violated_at), "escalation": row.escalation or 0,
            "created_at": iso(row.created_at), "updated_at": iso(row.updated_at)}


def _post(c: dict[str, Any], op: str, by: str, note: str = "") -> str:
    """The operation as a commitment.v1 message, replying to the decision it came from.
    Called after the commitment is stored, outside its session."""
    from ma_pmo.core import protocol
    from ma_pmo.core.schemas.message import AgentMessage, Intent, MessagePayload

    return protocol.publish(AgentMessage(
        sender=by, receiver=c["creditor"] if by == c["debtor"] else c["debtor"],
        intent=Intent.INFORM, task_ref=c["project_id"] or c["id"],
        payload=MessagePayload(schema_="commitment.v1", data={
            "commitment_id": c["id"], "op": op, "state": c["state"], "debtor": c["debtor"],
            "creditor": c["creditor"], "consequent": c["consequent"], "due": c["due"],
            "project_id": c["project_id"], "by": by, "note": note}),
        conversation_id=c["conversation_id"], in_reply_to=c["source_message"])).message_id


def create(*, kind: str, debtor: str, creditor: str, consequent: str, by: str,
           antecedent: str | None = None, due: str | datetime | None = None,
           detach_by: str | datetime | None = None, project_id: str | None = None,
           source_message: str | None = None, source_decision: str | None = None,
           source_approval: int | None = None, check: dict | None = None) -> dict[str, Any]:
    """A new commitment; the same consequent from the same source is not created twice."""
    now = _now()
    conversation = None
    with get_session() as s:
        if source_message:
            same = s.scalars(select(Commitment).where(
                Commitment.source_message == source_message,
                Commitment.consequent == consequent)).first()
            if same is not None:
                return as_dict(same)
            msg = s.get(AgentMessageRow, source_message)
            conversation = msg.conversation_id if msg is not None else None
        row = Commitment(
            id=f"COM-{uuid.uuid4().hex[:10]}", kind=kind, debtor=debtor, creditor=creditor,
            antecedent=antecedent, consequent=consequent, detach_by=_date(detach_by),
            due=_date(due) or _today() + timedelta(days=get_settings().commitment_due_days),
            state=CONDITIONAL if antecedent else ACTIVE, project_id=project_id,
            source_message=source_message, source_decision=source_decision,
            source_approval=source_approval, conversation_id=conversation, check=check,
            history=[{"op": "create", "by": by, "at": iso(now), "note": ""}],
            created_at=now, updated_at=now)
        s.add(row)
        s.flush()
        made = as_dict(row)
    _post(made, "create", by)
    return made


# op -> (states it applies to, state after; None keeps the state)
_OPS: dict[str, tuple[set[str], str | None]] = {
    "detach": ({CONDITIONAL}, ACTIVE),
    "discharge": (OPEN, SATISFIED),
    "release": (OPEN | {VIOLATED}, RELEASED),
    "delegate": (OPEN, None),
    "assign": (OPEN, None),
}


def apply(commitment_id: str, op: str, *, by: str, note: str = "", to: str | None = None,
          evidence: list[dict] | None = None) -> dict[str, Any]:
    """Run one operation. KeyError if there is no such commitment here; ValueError if the
    operation does not apply to its state, or a delegate/assign names nobody."""
    with get_session() as s:
        row = s.scalars(select(Commitment).where(Commitment.id == commitment_id)).first()
        if row is None:
            raise KeyError(commitment_id)
        if op == "cancel":  # Singh: cancelling an active commitment violates it
            allowed, after = OPEN, VIOLATED if row.state == ACTIVE else CANCELLED
        elif op in _OPS:
            allowed, after = _OPS[op][0], _OPS[op][1] or row.state
        else:
            raise ValueError(f"unknown operation: {op}")
        if row.state not in allowed:
            raise ValueError(tr(f"cannot {op} a {row.state} commitment",
                                f"{row.state} 상태의 약속에는 {op}을(를) 할 수 없습니다"))
        if op in {"delegate", "assign"}:
            if not (to or "").strip():
                raise ValueError(tr(f"{op} needs someone to hand it to",
                                    f"{op}에는 넘겨받을 사람이 필요합니다"))
            if op == "delegate":
                row.debtor = to.strip()  # type: ignore[union-attr]
            else:
                row.creditor = to.strip()  # type: ignore[union-attr]
        if op == "discharge":
            row.evidence = [*(row.evidence or []), *(evidence or [])]
        row.state, row.updated_at = after, _now()
        row.history = [*(row.history or []),
                       {"op": op, "by": by, "at": iso(row.updated_at), "note": note,
                        **({"to": to} if to else {})}]
        done = as_dict(row)
    _post(done, op, by, note)
    return done


def get(commitment_id: str) -> dict[str, Any] | None:
    with get_session() as s:
        row = s.scalars(select(Commitment).where(Commitment.id == commitment_id)).first()
        return as_dict(row) if row else None


def list_open(*, state: str | None = None, debtor: str | None = None,
              project: str | None = None, source_message: str | None = None,
              limit: int = 200) -> list[dict[str, Any]]:
    with get_session() as s:
        q = select(Commitment).order_by(Commitment.due, Commitment.created_at)
        if state:
            q = q.where(Commitment.state == state)
        if debtor:
            q = q.where(Commitment.debtor == debtor)
        if project:
            q = q.where(Commitment.project_id == project)
        if source_message:
            q = q.where(Commitment.source_message == source_message)
        return [as_dict(r) for r in s.scalars(q.limit(limit)).all()]


# ── where commitments come from ───────────────────────────────────────────────────────

def from_gate(message_id: str, *, creditor: str, by: str,
              decision_id: str | None = None, approval_id: int | None = None) -> list[dict]:
    """A conditional gate's conditions, owed by the project team, once the gate is in force.

    Each one remembers which criterion it stands for, so the tracker can discharge it when
    that criterion passes.
    """
    with get_session() as s:
        row = s.get(AgentMessageRow, message_id)
        payload = (row.payload or {}) if row is not None else {}
        task_ref = row.task_ref if row is not None else ""
    data = payload.get("data") or {}
    if payload.get("schema") != "gate_review.v1" or data.get("decision") != "conditional":
        return []
    checklist = data.get("checklist") or []
    made = []
    for condition in data.get("conditions") or []:
        index = next((i for i, c in enumerate(checklist)
                      if not c.get("passed") and condition.startswith(c.get("criterion", ""))),
                     None)
        made.append(create(
            kind="gate_condition", debtor=data["project_id"], creditor=creditor,
            consequent=condition, by=by, project_id=data["project_id"],
            source_message=message_id, source_decision=decision_id, source_approval=approval_id,
            check=None if index is None else {
                "kind": "gate_criterion", "gate": data.get("gate"), "index": index,
                "scope": task_ref.split("/")[0] or None}))
    return made


def adoptable(message_id: str, adopt: list[str] | None) -> list[dict]:
    """The alternatives offered for this decision that a person picked; ValueError for any
    that was not offered for it (checked before the approval is recorded)."""
    offers = []
    with get_session() as s:
        for alt_id in adopt or []:
            alt = s.get(AgentMessageRow, alt_id)
            data = ((alt.payload or {}).get("data") or {}) if alt is not None else {}
            if data.get("verdict") != "ALTERNATIVE" or data.get("target") != message_id:
                raise ValueError(tr(f"{alt_id} is not an alternative offered for this decision",
                                    f"{alt_id}은(는) 이 결정에 제시된 대안이 아닙니다"))
            offers.append({**(data.get("alternative") or {}), "rationale": data.get("rationale")})
    return offers


def from_approval(message_id: str, *, approver: str, approval_id: int,
                  decision_id: str | None, conditions: list[dict] | None,
                  adopt: list[str] | None) -> list[dict]:
    """Conditions a person attached when approving, and alternatives they adopted."""
    with get_session() as s:
        row = s.get(AgentMessageRow, message_id)
        data = ((row.payload or {}).get("data") or {}) if row is not None else {}
        sender = row.sender if row is not None else approver
    project = data.get("project_id")
    made = []
    for c in conditions or []:
        made.append(create(
            kind="approval_condition", debtor=(c.get("debtor") or project or sender),
            creditor=approver, consequent=c["text"], due=c.get("due"), by=approver,
            project_id=project, source_message=message_id, source_decision=decision_id,
            source_approval=approval_id))
    for offer in adoptable(message_id, adopt):
        made.append(create(
            kind="alternative", debtor=project or sender, creditor=approver,
            consequent=offer.get("summary") or offer.get("rationale") or "",
            due=offer.get("until"), by=approver, project_id=project,
            source_message=message_id, source_decision=decision_id,
            source_approval=approval_id))
    return made


# ── the tracker discharges what it can see ────────────────────────────────────────────

def check_tracker(tracker: Any = None) -> list[dict]:
    """Discharge open gate conditions whose criterion now passes; returns those discharged."""
    from ma_pmo.agents import common
    from ma_pmo.agents.gates import evaluate_gate
    from ma_pmo.core.scope import DEFAULT_SCOPE
    from ma_pmo.integrations.registry import get_tracker

    tracker = tracker or get_tracker()
    with get_session() as s:
        due: list[tuple[str, str, dict]] = [
            (r.id, r.project_id, r.check) for r in s.scalars(select(Commitment).where(
                Commitment.state.in_(OPEN)))
            if r.check and r.project_id and r.check.get("kind") == "gate_criterion"]
    done = []
    for cid, project_id, check in due:
        project = common.find_project(tracker, check.get("scope") or DEFAULT_SCOPE, project_id)
        if project is None:
            continue
        with use_lang("en"):  # criteria are matched by position; names only for the record
            _, criteria, _ = evaluate_gate(project, check["gate"])
        if check["index"] < len(criteria) and criteria[check["index"]].passed:
            name = criteria[check["index"]].name
            done.append(apply(cid, "discharge", by=TRACKER, note=f"{name}: passes now",
                              evidence=[{"kind": "tracker", "ref": project_id,
                                         "field": name}]))
    return done


# ── due dates and escalation ──────────────────────────────────────────────────────────

ENGINE = "due-dates"
# what each step of the chain does, in order, after the violation itself
CHAIN = ("debtor", "accountable", "reopen")


def sweep(now: datetime | None = None) -> dict[str, list[str]]:
    """Violate overdue commitments, expire undetached ones, and take the escalation steps that
    are due. Idempotent: each transition and each step happens once."""
    now = now or _today()
    every = timedelta(days=get_settings().commitment_escalate_days)
    with get_session() as s:
        rows = s.scalars(select(Commitment).where(Commitment.state.in_(OPEN | {VIOLATED}))).all()
        overdue = [r.id for r in rows if r.state == ACTIVE and r.due and r.due < now]
        lapsed = [r.id for r in rows
                  if r.state == CONDITIONAL and r.detach_by and r.detach_by < now]
        steps = {r.id: (r.escalation, r.violated_at) for r in rows if r.state == VIOLATED}
    out: dict[str, list[str]] = {"violated": [], "expired": [], "escalated": [], "reopened": []}
    for cid in lapsed:
        _transition(cid, EXPIRED, "expire", tr("antecedent did not hold in time",
                                               "전제 조건이 기한 안에 충족되지 않음"))
        out["expired"].append(cid)
    for cid in overdue:
        _transition(cid, VIOLATED, "violate", tr("due date passed", "기한이 지남"), when=now)
        out["violated"].append(cid)
        steps[cid] = (0, now)
    for cid, (done, since) in steps.items():
        since = since or now
        while done < len(CHAIN) and since + every * done <= now:
            kind = _escalate(cid, CHAIN[done])
            out["reopened" if kind == "reopen" else "escalated"].append(cid)
            done += 1
    return out


def _transition(cid: str, state: str, op: str, note: str, when: datetime | None = None) -> None:
    with get_session() as s:
        row = s.scalars(select(Commitment).where(Commitment.id == cid)).one()
        row.state, row.updated_at = state, _now()
        if state == VIOLATED:
            row.violated_at = when
        row.history = [*(row.history or []), {"op": op, "by": ENGINE, "at": iso(row.updated_at),
                                               "note": note}]
        c = as_dict(row)
    _post(c, op, ENGINE, note)


def _escalate(cid: str, step: str) -> str:
    """One step of the chain: a message, a notification, and for the last one a reopened
    decision. The step is counted first, so a failure cannot repeat it."""
    with get_session() as s:
        row = s.scalars(select(Commitment).where(Commitment.id == cid)).one()
        row.escalation += 1
        level = row.escalation
        who = {"debtor": row.debtor, "accountable": row.creditor}.get(step)
        note = (tr(f"step {level}: reopened the decision", f"{level}단계: 결정 재검토")
                if step == "reopen"
                else tr(f"step {level}: told {who}", f"{level}단계: {who}에게 알림"))
        row.history = [*(row.history or []), {"op": "escalate", "by": ENGINE, "at": iso(_now()),
                                               "note": note, "step": step}]
        c = as_dict(row)
    message_id = _post(c, "escalate", ENGINE, note)
    if step == "reopen":
        _reopen(c)
    _notify(c, step, who, message_id)
    return step


def _reopen(c: dict[str, Any]) -> None:
    """The decision goes back to the approval queue, with the missed obligation as the reason."""
    from ma_pmo.core import decisions
    from ma_pmo.db.models import Approval

    why = tr(f"missed: {c['consequent']} (due {c['due'][:10]})",
             f"미이행: {c['consequent']} (기한 {c['due'][:10]})")
    if c["source_decision"]:
        decisions.reopen(c["source_decision"], why)
    if c["source_message"]:
        with get_session() as s:
            s.add(Approval(message_id=c["source_message"], decision="pending", reason={
                "kind": "reopened", "commitment": c["id"], "consequent": c["consequent"],
                "due": c["due"], "decision_record": c["source_decision"]}))


def _notify(c: dict[str, Any], step: str, who: str | None, message_id: str) -> None:
    from ma_pmo.integrations.base import Event, EventType
    from ma_pmo.integrations.dispatch import emit_later

    kind = {"debtor": EventType.COMMITMENT_VIOLATED, "accountable": EventType.COMMITMENT_ESCALATED,
            "reopen": EventType.DECISION_REOPENED}[step]
    title = {
        "debtor": tr(f"Missed: {c['consequent']}", f"미이행: {c['consequent']}"),
        "accountable": tr(f"Still missed, escalated to {who}: {c['consequent']}",
                          f"계속 미이행, {who}에게 보고: {c['consequent']}"),
        "reopen": tr(f"Decision reopened: {c['consequent']} was not met",
                     f"결정 재검토: {c['consequent']} 미이행"),
    }[step]
    emit_later([Event(type=kind, title=title,
                      severity="critical" if step == "reopen" else "warning",
                      summary=tr(f"owed by {c['debtor']} to {c['creditor']}, due {c['due'][:10]}",
                                 f"{c['debtor']} → {c['creditor']}, 기한 {c['due'][:10]}"),
                      task_ref=c["project_id"] or "", data={
                          "message_id": message_id, "commitment_id": c["id"], "to": who or "",
                          "decision_record": c["source_decision"], "step": step})])


def sweep_quietly() -> None:
    """A sweep that never fails its caller (before a run, on a webhook)."""
    try:
        sweep()
    except Exception as e:  # the due-date engine must not stop the work it watches
        from ma_pmo.core.obs import get_logger

        get_logger("commitments").warning("sweep_failed", error=str(e)[:200])


def violated_for(project_id: str) -> list[str]:
    """What a project failed to deliver: a risk signal for A4."""
    with get_session() as s:
        return [r.consequent for r in s.scalars(select(Commitment).where(
            Commitment.project_id == project_id, Commitment.state == VIOLATED))]
