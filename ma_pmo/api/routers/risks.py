"""GET /risks — the register of detected risks (A4 output)."""
from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import select

from ma_pmo.db.models import Risk
from ma_pmo.db.session import get_session

router = APIRouter(tags=["risks"])


@router.get("/risks")
def list_risks(project_id: str | None = None, limit: int = 100) -> list[dict]:
    with get_session() as s:
        stmt = select(Risk).order_by(Risk.detected_at.desc()).limit(limit)
        if project_id:
            stmt = stmt.where(Risk.project_id == project_id)
        rows = s.scalars(stmt).all()
        return [
            {
                "id": r.id,
                "project_id": r.project_id,
                "signal": r.signal,
                "severity": r.severity,
                "detected_at": r.detected_at.isoformat() if r.detected_at else None,
                "materialized_at": r.materialized_at.isoformat() if r.materialized_at else None,
                "mitigation": r.mitigation,
            }
            for r in rows
        ]
