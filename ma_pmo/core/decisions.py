"""Decision records: every decision in one place, in MADR form (roadmap 8, step 2).

A PMO has to answer later who decided what, why, whom they consulted and whom they told.
Decisions used to be spread over approvals, run state, workflow versions, recommendations and
budgets. Each now also leaves a `decision_record`:

- `kind`, `subject`, `title`: gate (project/gate), report, risk, allocation, schedule,
  workflow_publish, model_recommendation, budget
- `status`: `proposed` (held for a person), `committed` (the commit gate let it through),
  `accepted` / `rejected` (a person decided), `superseded` (a newer one for the same subject),
  `reopened` (an obligation it created was missed; back in the approval queue)
- `drivers`: the evidence the message cites
- `options`: the decision and the alternatives review offered
- `outcome`: what was chosen, and the person's reason (`rationale`)
- `decision_makers`: the agent that proposed it and the person who decided, with roles
- `consulted`: the reviewers and their verdicts
- `informed`: who was told: read from the communication log when one record is fetched
- `consequences`: conditions attached, follow-ups

A person must give a reason to reject, and to approve a decision review challenged (an
override; EU AI Act Art. 14(4)(d)). Sources: MADR template, Nygard ADRs, PMBOK decision log.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select

from ma_pmo.core.times import iso
from ma_pmo.db.models import DecisionRecord
from ma_pmo.db.session import get_session

KINDS = {"gate_review.v1": "gate", "report.v1": "report", "risk_alert.v1": "risk",
         "allocation.v1": "allocation", "schedule.v1": "schedule"}
FINAL = {"rejected", "superseded"}


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def describe(schema: str | None, data: dict[str, Any], task_ref: str = "") -> tuple[str, str, str]:
    """(kind, subject, title) of an agent's decision from its payload."""
    kind = KINDS.get(schema or "", "other")
    project = data.get("project_id")
    if kind == "gate":
        subject = f"{project}/{data.get('gate')}"
        return kind, subject, f"{project} {data.get('gate')} → {data.get('decision')}"
    if kind == "risk":
        return kind, f"{project}/risk", f"{project} risk {data.get('severity')}"
    if kind == "report":
        scope = data.get("scope") or task_ref
        return kind, f"{scope}/report", f"Report · {scope}"
    if project:
        return kind, f"{project}/{kind}", f"{project} {kind}"
    return kind, task_ref or kind, f"{kind} · {task_ref}"


def _named(kind: str, project: str | None, fields: dict[str, Any]) -> dict[str, Any]:
    """Add the people roles name for this kind of decision (roadmap 9): A among the decision
    makers, C among the consulted, I among the informed."""
    from ma_pmo.core import roles

    people = roles.raci(kind, project)
    extra = {"decision_makers": [{"who": p, "role": "accountable"} for p in people["A"]],
             "consulted": [{"who": p, "role": "consulted"} for p in people["C"]],
             "informed": [{"who": p, "role": "informed"} for p in people["I"]]}
    return {**fields, **{k: [*(fields.get(k) or []), *v] for k, v in extra.items() if v}}


def record(kind: str, subject: str, title: str, status: str, project: str | None = None,
           **fields: Any) -> dict[str, Any]:
    """Store a decision; an earlier live one of the same kind and subject becomes superseded."""
    fields = _named(kind, project or _project_of(kind, subject), fields)
    now = _now()
    with get_session() as s:
        earlier = s.scalars(select(DecisionRecord)
                            .where(DecisionRecord.kind == kind, DecisionRecord.subject == subject)
                            .order_by(DecisionRecord.created_at.desc())).first()
        supersedes = None
        if earlier is not None and earlier.status not in FINAL:
            earlier.status, earlier.updated_at = "superseded", now
            supersedes = earlier.id
        row = DecisionRecord(id=f"DEC-{uuid.uuid4().hex[:10]}", kind=kind, subject=subject,
                             title=title, status=status, supersedes=supersedes, created_at=now,
                             updated_at=now, **fields)
        s.add(row)
        s.flush()
        return as_dict(row)


def _project_of(kind: str, subject: str) -> str | None:
    """Agent decisions are about a project: PROJ-31/G3-execution, PROJ-31/risk, ..."""
    head = subject.split("/")[0]
    return head if "/" in subject and kind not in {"report", "workflow_publish"} else None


def for_message(message_id: str) -> dict[str, Any] | None:
    with get_session() as s:
        row = s.scalars(select(DecisionRecord).where(DecisionRecord.message_id == message_id)
                        .order_by(DecisionRecord.created_at.desc())).first()
        return as_dict(row) if row else None


def decided_by_person(message_id: str, *, kind: str, subject: str, title: str, approver: str,
                      decision: str, rationale: str | None, approval_id: int,
                      run_id: str | None, agent: str, evidence: list | None) -> dict[str, Any]:
    """A person approved or rejected an agent's decision: update its record, or start one."""
    status = "accepted" if decision == "approve" else "rejected"
    person = {"who": approver, "role": "approver"}
    outcome = {"chosen": decision, "justification": rationale}
    with get_session() as s:
        row = s.scalars(select(DecisionRecord).where(DecisionRecord.message_id == message_id)
                        .order_by(DecisionRecord.created_at.desc())).first()
        if row is not None:
            row.status, row.outcome, row.approval_id = status, outcome, approval_id
            row.decision_makers = [*(row.decision_makers or []), person]
            row.updated_at = _now()
            return as_dict(row)
    return record(kind, subject, title, status, outcome=outcome, approval_id=approval_id,
                  decision_makers=[{"who": agent, "role": "proposer"}, person],
                  drivers=evidence or [], run_id=run_id, message_id=message_id)


def by_person(kind: str, subject: str, title: str, who: str, chosen: str,
              rationale: str | None = None, **fields: Any) -> dict[str, Any]:
    """A decision a person made directly (publishing a workflow, a budget, a recommendation)."""
    return record(kind, subject, title, "accepted",
                  outcome={"chosen": chosen, "justification": rationale},
                  decision_makers=[{"who": who, "role": "decider"}], **fields)


def reopen(record_id: str, why: str) -> dict[str, Any] | None:
    """Put a decision back under review (an obligation it created was not met)."""
    with get_session() as s:
        row = s.scalars(select(DecisionRecord).where(DecisionRecord.id == record_id)).first()
        if row is None:
            return None
        row.status, row.updated_at = "reopened", _now()
        row.consequences = [*(row.consequences or []), why]
        return as_dict(row)


def as_dict(row: DecisionRecord) -> dict[str, Any]:
    return {
        "id": row.id, "kind": row.kind, "subject": row.subject, "title": row.title,
        "status": row.status, "context": row.context, "drivers": row.drivers or [],
        "options": row.options or [], "outcome": row.outcome or {},
        "decision_makers": row.decision_makers or [], "consulted": row.consulted or [],
        "informed": row.informed or [], "consequences": row.consequences or [],
        "supersedes": row.supersedes, "run_id": row.run_id, "message_id": row.message_id,
        "approval_id": row.approval_id, "created_at": iso(row.created_at),
        "updated_at": iso(row.updated_at),
    }


def list_records(kind: str | None = None, status: str | None = None,
                 subject: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
    with get_session() as s:
        q = select(DecisionRecord).order_by(DecisionRecord.created_at.desc())
        if kind:
            q = q.where(DecisionRecord.kind == kind)
        if status:
            q = q.where(DecisionRecord.status == status)
        if subject:
            q = q.where(DecisionRecord.subject.like(f"{subject}%"))
        return [as_dict(r) for r in s.scalars(q.limit(limit)).all()]


def get(record_id: str) -> dict[str, Any] | None:
    from ma_pmo.core import communications

    with get_session() as s:  # a select, so the workspace filter applies
        row = s.scalars(select(DecisionRecord).where(DecisionRecord.id == record_id)).first()
        found = as_dict(row) if row else None
    if found is not None:
        found["informed"] = found["informed"] + communications.informed(found["id"],
                                                                        found["message_id"])
    return found
