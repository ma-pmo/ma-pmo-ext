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
- `violated` when cancelled while active (and, from roadmap 9 step 2, when its due date passes),
  `cancelled` when cancelled while still conditional, `released` when its creditor lets it go;
- delegated (new debtor) or assigned (new creditor) without changing its state.

Every operation is also a `commitment.v1` message in the conversation of the decision it came
from, replying to that decision, so nothing changes silently.
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
            "created_at": iso(row.created_at), "updated_at": iso(row.updated_at)}


def _post(c: dict[str, Any], op: str, by: str, note: str = "") -> None:
    """The operation as a commitment.v1 message, replying to the decision it came from.
    Called after the commitment is stored, outside its session."""
    from ma_pmo.core import protocol
    from ma_pmo.core.schemas.message import AgentMessage, Intent, MessagePayload

    protocol.publish(AgentMessage(
        sender=by, receiver=c["creditor"] if by == c["debtor"] else c["debtor"],
        intent=Intent.INFORM, task_ref=c["project_id"] or c["id"],
        payload=MessagePayload(schema_="commitment.v1", data={
            "commitment_id": c["id"], "op": op, "state": c["state"], "debtor": c["debtor"],
            "creditor": c["creditor"], "consequent": c["consequent"], "due": c["due"],
            "project_id": c["project_id"], "by": by, "note": note}),
        conversation_id=c["conversation_id"], in_reply_to=c["source_message"]))


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
    "release": (OPEN, RELEASED),
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
