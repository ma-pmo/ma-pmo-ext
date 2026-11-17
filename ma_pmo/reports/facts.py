"""The facts under a report: computed from the tracker and the previous report, never by an LLM.

| fact | rule |
|---|---|
| progress | mean of the projects' effort-weighted progress |
| SPI | portfolio EV / PV over every task (EV: completion-weighted effort, PV: total effort) |
| red, amber | projects with that status |
| late projects | CPM finish past the deadline by more than the schedule tolerance |
| worst slack | smallest deadline − forecast finish, in days |
| previous | the same fact in the latest earlier report of the scope |
| tolerance | SPI < `MA_PMO_TOLERANCE_SPI`; finish > deadline + `MA_PMO_TOLERANCE_SLIP_DAYS` |
| overall | the worst project status, at least amber when a tolerance is breached |

Reports stored before report.v2 have no facts; their project lines still give the previous status
and progress.
"""
from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any, Literal

from sqlalchemy import select

from ma_pmo.agents import common
from ma_pmo.agents.cpm import compute_cpm
from ma_pmo.core.config import get_settings
from ma_pmo.core.i18n import tr
from ma_pmo.core.schemas.payloads.report_v2 import (
    KpiFact,
    ProjectFact,
    ReportFacts,
    Status,
    ToleranceCheck,
)
from ma_pmo.db.models import Report
from ma_pmo.db.session import get_session

_RANK = {"green": 0, "amber": 1, "red": 2}


def _slack_days(deadline: str | None, finish: str | None) -> int | None:
    if not deadline or not finish:
        return None
    try:
        return (date.fromisoformat(deadline) - date.fromisoformat(finish)).days
    except ValueError:
        return None


def _portfolio_spi(projects: list[dict]) -> float | None:
    tasks = [t for p in projects for t in p.get("tasks", [])]
    return common.spi({"tasks": tasks})


def previous_report(scope: str) -> tuple[str, str, dict[str, Any]] | None:
    """(id, as-of date, content) of the latest stored report of `scope` in this workspace."""
    with get_session() as s:
        row = s.scalars(select(Report).where(Report.scope == scope)
                        .order_by(Report.created_at.desc())).first()
        if row is None:
            return None
        as_of = (row.content.get("facts") or {}).get("as_of") or row.created_at.date().isoformat()
        return row.id, as_of, dict(row.content)


def build(status: dict, previous: tuple[str, str, dict[str, Any]] | None = None, *,
          today: date | None = None) -> ReportFacts:
    """Facts for the portfolio `status` (as a tracker returns it), compared with `previous`."""
    settings = get_settings()
    projects = status.get("projects", [])
    prev_id, prev_as_of, prev = previous or (None, None, {})
    prev_kpis = {k["id"]: k.get("value") for k in (prev.get("facts") or {}).get("kpis", [])}
    prev_lines = {p["project_id"]: p for p in prev.get("project_status", [])}

    project_facts, checks = [], []
    for p in projects:
        pid = p["project_id"]
        cpm = compute_cpm(p.get("tasks", []))
        finish = cpm.projected_finish(p.get("planned_start"))
        slack = _slack_days(p.get("deadline"), finish)
        spi = common.spi(p)
        before = prev_lines.get(pid, {})
        project_facts.append(ProjectFact(
            id=f"project.{pid}", project_id=pid, status=p.get("status", "green"),
            previous_status=before.get("status"),
            percent_complete=p.get("percent_complete", 0.0),
            previous_percent_complete=before.get("percent_complete"),
            spi=spi, deadline=p.get("deadline"), forecast_finish=finish, slack_days=slack,
        ))
        if slack is not None:
            late = -slack
            checks.append(ToleranceCheck(
                id=f"tolerance.{pid}.schedule", project_id=pid, dimension="schedule",
                value=late, limit=settings.tolerance_slip_days,
                breached=late > settings.tolerance_slip_days))
        if spi is not None:
            checks.append(ToleranceCheck(
                id=f"tolerance.{pid}.spi", project_id=pid, dimension="spi", value=spi,
                limit=settings.tolerance_spi, breached=spi < settings.tolerance_spi))

    late_projects = {c.project_id for c in checks if c.dimension == "schedule" and c.breached}
    slacks = [f.slack_days for f in project_facts if f.slack_days is not None]
    progress = (round(sum(f.percent_complete for f in project_facts) / len(project_facts), 1)
                if project_facts else None)

    def kpi(id_: str, label: str, value: float | None, unit: str = "",
            better: Literal["higher", "lower"] = "higher") -> KpiFact:
        return KpiFact(id=id_, label=label, value=value, previous=prev_kpis.get(id_),
                       unit=unit, better=better)

    kpis = [
        kpi("kpi.progress", tr("Average progress", "평균 진척"), progress, "%"),
        kpi("kpi.spi", tr("Portfolio SPI", "포트폴리오 SPI"), _portfolio_spi(projects)),
        kpi("kpi.red", tr("Red projects", "red 프로젝트"),
            sum(f.status == "red" for f in project_facts), better="lower"),
        kpi("kpi.amber", tr("Amber projects", "amber 프로젝트"),
            sum(f.status == "amber" for f in project_facts), better="lower"),
        kpi("kpi.late", tr("Projects past deadline (forecast)", "마감 초과 예상 프로젝트"),
            len(late_projects), better="lower"),
        kpi("kpi.worst_slack", tr("Worst slack", "최소 여유"),
            min(slacks) if slacks else None, tr("days", "일")),
    ]
    return ReportFacts(
        as_of=(today or datetime.now(UTC).date()).isoformat(),
        period_start=prev_as_of, previous_report_id=prev_id,
        kpis=kpis, projects=project_facts, tolerances=checks,
    )


def overall_status(facts: ReportFacts) -> Status:
    worst: Status = max((f.status for f in facts.projects), key=_RANK.__getitem__,
                        default="green")
    if facts.breaches and worst == "green":
        return "amber"
    return worst
