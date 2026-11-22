"""The communication log: what was told to whom, and whether it got there (roadmap 8, step 3).

`integrations/dispatch.py` writes a row per notification attempt, skips included. This module
reads them back for the API and for the decision log, whose `informed` lists the channels a
decision's notifications reached.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import or_, select

from ma_pmo.core.times import iso
from ma_pmo.db.models import Communication
from ma_pmo.db.session import get_session


def as_dict(row: Communication) -> dict[str, Any]:
    return {"id": row.id, "event": row.event, "channel": row.channel, "target": row.target,
            "title": row.title, "severity": row.severity, "status": row.status,
            "error": row.error, "message_id": row.message_id, "decision_id": row.decision_id,
            "approval_id": row.approval_id, "run_id": row.run_id,
            "created_at": iso(row.created_at)}


def list_log(*, event: str | None = None, status: str | None = None, run: str | None = None,
             message: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
    with get_session() as s:
        q = select(Communication).order_by(Communication.id.desc())
        if event:
            q = q.where(Communication.event == event)
        if status:
            q = q.where(Communication.status == status)
        if run:
            q = q.where(Communication.run_id == run)
        if message:
            q = q.where(Communication.message_id == message)
        return [as_dict(r) for r in s.scalars(q.limit(limit)).all()]


def informed(decision_id: str, message_id: str | None) -> list[dict[str, Any]]:
    """Every notification about a decision: its message's events and its approval's."""
    with get_session() as s:
        about = [Communication.decision_id == decision_id]
        if message_id:
            about.append(Communication.message_id == message_id)
        rows = s.scalars(select(Communication).where(or_(*about))
                         .order_by(Communication.id)).all()
        return [{"channel": r.channel, "event": r.event, "status": r.status, "error": r.error,
                 "at": iso(r.created_at)} for r in rows]
