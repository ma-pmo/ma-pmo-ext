"""GET /messages — audit log of structured messages between agents (§4, append-only).

GET /messages               : newest first (?task_ref=, ?sender=, ?conversation=, ?limit=)
GET /messages/{id}/thread   : the message's conversation in time order, with replies

All agent communication is stored in an immutable log for auditability and
reproducibility. Lists behavior (who sent what to whom) in time order.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from ma_pmo.core.protocol import message_dict
from ma_pmo.db.models import AgentMessageRow
from ma_pmo.db.session import get_session

router = APIRouter(tags=["messages"])


@router.get("/messages")
def list_messages(
    task_ref: str | None = None, sender: str | None = None, conversation: str | None = None,
    limit: int = 100,
) -> list[dict]:
    with get_session() as s:
        stmt = select(AgentMessageRow).order_by(AgentMessageRow.timestamp.desc()).limit(limit)
        if task_ref:
            stmt = stmt.where(AgentMessageRow.task_ref.like(f"{task_ref}%"))
        if sender:
            stmt = stmt.where(AgentMessageRow.sender == sender)
        if conversation:
            stmt = stmt.where(AgentMessageRow.conversation_id == conversation)
        rows = s.scalars(stmt).all()
        return [message_dict(r) for r in rows]


@router.get("/messages/{message_id}/thread")
def message_thread(message_id: str) -> dict:
    """The conversation `message_id` belongs to, oldest first; `replies` maps a message id to
    the messages that answer it (a decision to its review verdicts)."""
    with get_session() as s:
        row = s.scalars(select(AgentMessageRow)
                        .where(AgentMessageRow.message_id == message_id)).first()
        if row is None:
            raise HTTPException(status_code=404, detail=f"unknown message {message_id!r}")
        if row.conversation_id is None:  # written before the envelope: the message alone
            rows = [row]
        else:
            rows = list(s.scalars(select(AgentMessageRow)
                                  .where(AgentMessageRow.conversation_id == row.conversation_id)
                                  .order_by(AgentMessageRow.timestamp)).all())
        replies: dict[str, list[str]] = {}
        for r in rows:
            if r.in_reply_to:
                replies.setdefault(r.in_reply_to, []).append(r.message_id)
        return {"conversation_id": row.conversation_id,
                "messages": [message_dict(r, payload=False) for r in rows], "replies": replies}
