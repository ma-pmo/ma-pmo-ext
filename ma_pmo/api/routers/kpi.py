"""GET /kpi — query and aggregate five-axis telemetry (§7)."""
from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import func, select

from ma_pmo.db.models import KpiEvent
from ma_pmo.db.session import get_session

router = APIRouter(tags=["kpi"])


@router.get("/kpi")
def list_kpi(axis: str | None = None, limit: int = 100) -> dict:
    with get_session() as s:
        stmt = select(KpiEvent).order_by(KpiEvent.ts.desc()).limit(limit)
        if axis:
            stmt = stmt.where(KpiEvent.axis == axis)
        rows = s.scalars(stmt).all()
        events = [
            {
                "axis": r.axis,
                "metric": r.metric,
                "value": r.value,
                "project_id": r.project_id,
                "meta": r.meta,
                "ts": r.ts.isoformat(),
            }
            for r in rows
        ]

        # summary per axis and metric
        agg = s.execute(
            select(
                KpiEvent.axis,
                KpiEvent.metric,
                func.count(),
                func.avg(KpiEvent.value),
                func.sum(KpiEvent.value),
            ).group_by(KpiEvent.axis, KpiEvent.metric)
        ).all()
    summary = [
        {"axis": a, "metric": m, "count": c, "avg": avg, "sum": total}
        for a, m, c, avg, total in agg
    ]
    return {"events": events, "summary": summary}
