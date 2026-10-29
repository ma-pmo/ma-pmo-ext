"""GET /messages — audit log of structured messages between agents (§4, append-only).

All agent communication is stored in an immutable log for auditability and
reproducibility. Lists behavior (who sent what to whom) in time order.
"""
from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import select

from ma_pmo.db.models import AgentMessageRow
from ma_pmo.db.session import get_session

router = APIRouter(tags=["messages"])


@router.get("/messages")
def list_messages(
    task_ref: str | None = None, sender: str | None = None, limit: int = 100
) -> list[dict]:
    with get_session() as s:
        stmt = select(AgentMessageRow).order_by(AgentMessageRow.timestamp.desc()).limit(limit)
        if task_ref:
            stmt = stmt.where(AgentMessageRow.task_ref.like(f"{task_ref}%"))
        if sender:
            stmt = stmt.where(AgentMessageRow.sender == sender)
        rows = s.scalars(stmt).all()
        return [
            {
                "message_id": r.message_id,
                "sender": r.sender,
                "receiver": r.receiver,
                "intent": r.intent,
                "schema": r.payload.get("schema") if isinstance(r.payload, dict) else None,
                "task_ref": r.task_ref,
                "confidence": r.confidence,
                "human_gate_required": r.human_gate_required,
                "payload": r.payload,
                "timestamp": r.timestamp.isoformat() if r.timestamp else None,
            }
            for r in rows
        ]
