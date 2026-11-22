"""Decision log and communication log (roadmap 8): every recorded decision, newest first, one
by id with whom it was told, and every notification attempt."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from ma_pmo.core import communications, decisions

router = APIRouter(tags=["decisions"])


@router.get("/decisions")
def list_decisions(kind: str | None = None, status: str | None = None,
                   subject: str | None = None,
                   limit: int = Query(100, ge=1, le=500)) -> list[dict]:
    return decisions.list_records(kind=kind, status=status, subject=subject, limit=limit)


@router.get("/decisions/{record_id}")
def get_decision(record_id: str) -> dict:
    found = decisions.get(record_id)
    if found is None:  # also a record in another workspace
        raise HTTPException(status_code=404, detail=f"decision {record_id} not found")
    return found


@router.get("/communications")
def list_communications(event: str | None = None, status: str | None = None,
                        run: str | None = None, message: str | None = None,
                        limit: int = Query(100, ge=1, le=500)) -> list[dict]:
    """Notification attempts, newest first: sent, failed, or skipped with the reason."""
    return communications.list_log(event=event, status=status, run=run, message=message,
                                   limit=limit)
