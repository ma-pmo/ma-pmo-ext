"""Earned value at an as-of date: one SPI and one forecast for every agent and report.

| figure | rule |
|---|---|
| as of | `MA_PMO_REPORT_AS_OF` if set, else today (UTC) |
| plan | the tracker's planned start and planned finish (the CPM finish when there is none) |
| EV | completion-weighted effort |
| PV | the total effort spread evenly over the plan, up to the as-of date |
| SPI | EV / PV; None before the planned start |
| forecast finish | planned start + planned duration / SPI; the planned finish before work starts |

Until 0.9 the agents' SPI was EV over the total effort, i.e. the completed share: a project half
done halfway through its plan scored 0.5, and gate G3's "SPI ≥ 0.8" failed every project in
progress. Past the planned finish the two agree, since PV is then the whole effort.
"""
from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from ma_pmo.agents.cpm import compute_cpm
from ma_pmo.core.config import get_settings


def as_of_date(value: str | None = None) -> date:
    text = value or get_settings().report_as_of
    return date.fromisoformat(text) if text else datetime.now(UTC).date()


def parse_day(text: str | None) -> date | None:
    try:
        return date.fromisoformat(text) if text else None
    except ValueError:
        return None


def plan_window(project: dict) -> tuple[date, date] | None:
    """(planned start, planned finish); the CPM finish when the tracker has no planned finish."""
    start = parse_day(project.get("planned_start"))
    if start is None:
        return None
    finish = parse_day(project.get("planned_finish"))
    if finish is None or finish <= start:
        finish = start + timedelta(days=max(1, compute_cpm(project.get("tasks", []))
                                            .project_duration))
    return start, finish


def values(project: dict, as_of: date | None = None) -> tuple[float, float]:
    """(EV, PV) of a project at `as_of`."""
    tasks = project.get("tasks", [])
    bac = sum(t.get("effort", 0.0) for t in tasks)
    ev = sum(t.get("effort", 0.0) * t.get("percent_complete", 0.0) / 100 for t in tasks)
    plan = plan_window(project)
    if plan is None:
        return ev, 0.0
    start, finish = plan
    day = as_of or as_of_date()
    share = min(1.0, max(0.0, (day - start).days / (finish - start).days))
    return ev, bac * share


def spi(project: dict, as_of: date | None = None) -> float | None:
    ev, pv = values(project, as_of)
    return round(ev / pv, 3) if pv > 0 else None


def forecast(project: dict, project_spi: float | None) -> str | None:
    """Forecast finish (ISO date): none when everything is done."""
    if project.get("percent_complete", 0.0) >= 100:
        return None
    plan = plan_window(project)
    if plan is None:
        return None
    start, finish = plan
    if not project_spi:  # not started (or no progress yet): the plan is all there is
        return finish.isoformat()
    return (start + timedelta(days=round((finish - start).days / project_spi))).isoformat()
