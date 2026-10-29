"""kpi_event aggregation utilities — shared base of the hypothesis harness."""
from __future__ import annotations

from sqlalchemy import func, select

from ma_pmo.db.models import KpiEvent
from ma_pmo.db.session import get_session


def metric_summary(metric: str) -> dict:
    """count/avg/min/max/sum of a single metric."""
    with get_session() as s:
        row = s.execute(
            select(
                func.count(),
                func.avg(KpiEvent.value),
                func.min(KpiEvent.value),
                func.max(KpiEvent.value),
                func.sum(KpiEvent.value),
            ).where(KpiEvent.metric == metric)
        ).one()
    count, avg, mn, mx, total = row
    return {"metric": metric, "count": count, "avg": avg, "min": mn, "max": mx, "sum": total}
