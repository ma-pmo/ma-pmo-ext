"""Human-in-the-loop approval gate — paper §8 governance.

High-risk decisions (budget, scope, contracts, external communication) are final only
after passing a human approval gate.
- LangGraph `interrupt` pauses the graph (approval node)
- the approval queue (approval table) lists and resolves pending items
- approval latency is measured as a KPI (cost axis)
"""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select

from ma_pmo.core import kpi
from ma_pmo.db.models import AgentMessageRow, Approval
from ma_pmo.db.session import get_session


def list_pending() -> list[dict]:
    """Pending approval items + a summary of the original message."""
    with get_session() as s:
        rows = s.execute(
            select(Approval, AgentMessageRow)
            .join(AgentMessageRow, Approval.message_id == AgentMessageRow.message_id)
            .where(Approval.decision == "pending")
        ).all()
        return [
            {
                "approval_id": a.id,
                "message_id": a.message_id,
                "sender": m.sender,
                "intent": m.intent,
                "task_ref": m.task_ref,
                "confidence": m.confidence,
                "payload": m.payload,
                "requested_at": m.timestamp.isoformat(),
            }
            for a, m in rows
        ]


def resolve(approval_id: int, *, approver: str, decision: str) -> dict:
    """Approve or reject. decision ∈ {approve, reject}. Records approval latency as a KPI."""
    if decision not in {"approve", "reject"}:
        raise ValueError("decision must be approve|reject")
    with get_session() as s:
        approval = s.get(Approval, approval_id)
        if approval is None:
            raise KeyError(f"approval {approval_id} not found")
        if approval.decision != "pending":
            raise ValueError(f"already resolved: {approval.decision}")

        msg = s.get(AgentMessageRow, approval.message_id)
        now = datetime.now(UTC)
        approval.decision = decision
        approval.approver = approver
        approval.decided_at = now

        if msg is not None:
            requested = msg.timestamp
            if requested.tzinfo is None:
                requested = requested.replace(tzinfo=UTC)
            latency = (now - requested).total_seconds()
            kpi.record_approval_latency(latency, message_id=approval.message_id)

        return {
            "approval_id": approval_id,
            "message_id": approval.message_id,
            "decision": decision,
            "approver": approver,
        }
