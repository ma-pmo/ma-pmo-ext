"""GET /risks — the register of detected risks (A4 output)."""
from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import select

from ma_pmo.core.times import iso
from ma_pmo.db.models import Project, Risk
from ma_pmo.db.session import get_session

router = APIRouter(tags=["risks"])


@router.get("/risks")
def list_risks(project_id: str | None = None, scope: str | None = None,
               limit: int = 100) -> list[dict]:
    with get_session() as s:
        stmt = select(Risk).order_by(Risk.detected_at.desc()).limit(limit)
        if project_id:
            stmt = stmt.where(Risk.project_id == project_id)
        if scope:
            stmt = stmt.where(Risk.project_id.in_(
                select(Project.id).where(Project.portfolio_id == scope)))
        rows = s.scalars(stmt).all()
        return [
            {
                "id": r.id,
                "project_id": r.project_id,
                "signal": r.signal,
                "severity": r.severity,
                "detected_at": iso(r.detected_at),
                "materialized_at": iso(r.materialized_at),
                "mitigation": r.mitigation,
            }
            for r in rows
        ]
