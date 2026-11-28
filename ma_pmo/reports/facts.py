"""The facts under a report: computed from the tracker, the board and the previous report, never by
an LLM.

| fact | rule |
|---|---|
| as of | the step's `as_of`, else `MA_PMO_REPORT_AS_OF`, else today (UTC) |
| progress | mean of the projects' effort-weighted progress |
| SPI | EV / PV at the as-of date. EV: completion-weighted effort. PV: the total effort spread |
|     | evenly from the planned start to the planned finish (CPM finish when there is none). |
|     | None before the planned start. |
| forecast finish | planned start + planned duration / SPI (the usual EVM time estimate); the |
|                 | planned finish before work starts; none when everything is done |
| slack | deadline − forecast finish, in days; negative is late |
| red, amber | projects with that status |
| late projects | forecast finish past the deadline by more than `MA_PMO_TOLERANCE_SLIP_DAYS` |
| tolerance | per project: SPI below `MA_PMO_TOLERANCE_SPI`; finish past the slip tolerance |
| previous | the same fact in the latest earlier report of the scope |
| risks, gates, lessons | A4's alerts, A6's gate decisions and A7's citations on the board, |
|                       | when the step can read them |
| approvals | decisions waiting in the approval queue for the scope's projects |
| overall | the worst project status, at least amber when a tolerance is breached |

Reports stored before report.v2 have no facts; their project lines still give the previous status
and progress.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Literal

from sqlalchemy import select

from ma_pmo.agents import evm
from ma_pmo.agents.evm import as_of_date
from ma_pmo.core.config import get_settings
from ma_pmo.core.i18n import tr
from ma_pmo.core.schemas.payloads.report_v2 import (
    ApprovalFact,
    GateFact,
    KpiFact,
    LessonFact,
    ProjectFact,
    ReportFacts,
    RiskFact,
    Status,
    ToleranceCheck,
)
from ma_pmo.db.models import Report
from ma_pmo.db.session import get_session

_RANK = {"green": 0, "amber": 1, "red": 2}


def _board_facts(board: list[dict], in_scope: set[str] | None) -> dict[str, Any]:
    def keep(pid: str) -> bool:
        return in_scope is None or pid in in_scope

    risks, gates, lessons = [], [], []
    for post in board:
        data, mid = post.get("data", {}), post.get("message_id", "")
        if post.get("schema") == "risk_alert.v1" and keep(data.get("project_id", "")):
            risks.append(RiskFact(id=f"risk.{mid}", project_id=data["project_id"],
                                  severity=data.get("severity", ""), signal=data.get("signal", ""),
                                  mitigation=data.get("mitigation", ""), message_id=mid))
        elif post.get("schema") == "gate_review.v1" and keep(data.get("project_id", "")):
            gates.append(GateFact(
                id=f"gate.{data['project_id']}.{data.get('gate', '')}",
                project_id=data["project_id"], gate=data.get("gate", ""),
                decision=data.get("decision", ""),
                failed=[c["criterion"] for c in data.get("checklist", []) if not c.get("passed")],
                conditions=data.get("conditions", []), message_id=mid))
        elif post.get("schema") == "knowledge.v1":
            lessons += [LessonFact(id=f"lesson.{c['source_id']}", source_id=c["source_id"],
                                   excerpt=c.get("excerpt", ""), message_id=mid)
                        for c in data.get("citations", [])]
    severity = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    risks.sort(key=lambda r: severity.get(r.severity, 4))
    return {"risks": risks, "gates": gates, "lessons": lessons}


# the tracker fields a project's line is computed from (status, progress, SPI, forecast, slack)
PROJECT_FIELDS = ("status", "percent_complete", "planned_start", "planned_finish", "deadline",
                  "tasks")


def evidence(facts: ReportFacts, status: dict) -> list[Any]:
    """What a report rests on: the messages it summarises (risks, gate reviews, lessons), the
    lessons themselves, and the tracker fields of each project line, each once."""
    from ma_pmo.core.schemas.message import EvidenceRef

    messages = ([r.message_id for r in facts.risks] + [g.message_id for g in facts.gates]
                + [n.message_id for n in facts.lessons])
    messages = [m for m in messages if m]
    refs = [EvidenceRef(kind="message", ref=m) for m in dict.fromkeys(messages)]
    refs += [EvidenceRef(kind="knowledge", ref=lid)
             for lid in dict.fromkeys(f.source_id for f in facts.lessons)]
    rows = {p["project_id"]: p for p in status.get("projects", [])}
    for line in facts.projects:
        row = rows.get(line.project_id) or {}
        refs += [EvidenceRef(kind="tracker", ref=line.project_id, field=f)
                 for f in PROJECT_FIELDS if f in row]
    return refs


def earlier_reports(scope: str, kind: str = "status", projects: list[str] | None = None,
                    n: int = 6) -> list[tuple[str, str, dict[str, Any]]]:
    """(id, as-of date, content) of up to `n` stored reports of the same scope, kind and
    projects in this workspace, newest first. Reports from before report.v2 count as status
    reports."""
    wanted = sorted(projects) if projects else None
    out = []
    with get_session() as s:
        rows = s.scalars(select(Report).where(Report.scope == scope)
                         .order_by(Report.created_at.desc()).limit(200)).all()
        for row in rows:
            facts = row.content.get("facts") or {}
            if (row.content.get("kind", "status") != kind
                    or facts.get("projects_in_scope") != wanted):
                continue
            as_of = facts.get("as_of") or row.created_at.date().isoformat()
            out.append((row.id, as_of, dict(row.content)))
            if len(out) == n:
                break
    return out


def previous_report(scope: str, kind: str = "status",
                    projects: list[str] | None = None) -> tuple[str, str, dict[str, Any]] | None:
    """The latest of `earlier_reports`, or None."""
    found = earlier_reports(scope, kind, projects, n=1)
    return found[0] if found else None


def build(status: dict, previous: tuple[str, str, dict[str, Any]] | None = None, *,
          today: date | None = None, projects: list[str] | None = None,
          board: list[dict] | None = None, steps: list[dict] | None = None) -> ReportFacts:
    """Facts for the portfolio `status` (as a tracker returns it), compared with `previous`.
    `projects` limits the report to some projects; `board` is what the step may read, and
    `steps` the steps it may read ({"step", "agent"})."""
    settings = get_settings()
    as_of = today or as_of_date()
    in_scope = set(projects) if projects else None
    rows = [p for p in status.get("projects", [])
            if in_scope is None or p["project_id"] in in_scope]
    prev_id, prev_as_of, prev = previous or (None, None, {})
    prev_kpis = {k["id"]: k.get("value") for k in (prev.get("facts") or {}).get("kpis", [])}
    # a report.v2 keeps each project's facts; older reports only their narrative lines
    prev_lines = {p["project_id"]: p for p in
                  (prev.get("facts") or {}).get("projects") or prev.get("project_status", [])}

    project_facts, checks = [], []
    ev_total = pv_total = 0.0
    for p in rows:
        pid = p["project_id"]
        ev, pv = evm.values(p, as_of)
        ev_total, pv_total = ev_total + ev, pv_total + pv
        spi = round(ev / pv, 3) if pv > 0 else None
        finish = evm.forecast(p, spi)
        deadline = evm.parse_day(p.get("deadline"))
        slack = (deadline - date.fromisoformat(finish)).days if finish and deadline else None
        before = prev_lines.get(pid, {})
        project_facts.append(ProjectFact(
            id=f"project.{pid}", project_id=pid, status=p.get("status", "green"),
            previous_status=before.get("status"),
            percent_complete=p.get("percent_complete", 0.0),
            previous_percent_complete=before.get("percent_complete"),
            spi=spi, deadline=p.get("deadline"), forecast_finish=finish, slack_days=slack,
        ))
        if slack is not None:
            checks.append(ToleranceCheck(
                id=f"tolerance.{pid}.schedule", project_id=pid, dimension="schedule",
                value=-slack, limit=settings.tolerance_slip_days,
                breached=-slack > settings.tolerance_slip_days))
        if spi is not None:
            checks.append(ToleranceCheck(
                id=f"tolerance.{pid}.spi", project_id=pid, dimension="spi", value=spi,
                limit=settings.tolerance_spi, breached=spi < settings.tolerance_spi))

    late = {c.project_id for c in checks if c.dimension == "schedule" and c.breached}
    slacks = [f.slack_days for f in project_facts if f.slack_days is not None]
    progress = (round(sum(f.percent_complete for f in project_facts) / len(project_facts), 1)
                if project_facts else None)

    def kpi(id_: str, label: str, value: float | None, unit: str = "",
            better: Literal["higher", "lower"] = "higher") -> KpiFact:
        return KpiFact(id=id_, label=label, value=value, previous=prev_kpis.get(id_),
                       unit=unit, better=better)

    kpis = [
        kpi("kpi.progress", tr("Average progress", "평균 진척"), progress, "%"),
        kpi("kpi.spi", tr("Schedule performance (SPI)", "일정 성과(SPI)"),
            round(ev_total / pv_total, 3) if pv_total > 0 else None),
        kpi("kpi.red", tr("Red projects", "red 프로젝트"),
            sum(f.status == "red" for f in project_facts), better="lower"),
        kpi("kpi.amber", tr("Amber projects", "amber 프로젝트"),
            sum(f.status == "amber" for f in project_facts), better="lower"),
        kpi("kpi.late", tr("Projects forecast late", "마감 초과 예상 프로젝트"),
            len(late), better="lower"),
        kpi("kpi.worst_slack", tr("Worst slack", "최소 여유"),
            min(slacks) if slacks else None, tr("days", "일")),
    ]
    return ReportFacts(
        as_of=as_of.isoformat(), projects_in_scope=sorted(in_scope) if in_scope else None,
        period_start=prev_as_of, previous_report_id=prev_id,
        kpis=kpis, projects=project_facts, tolerances=checks,
        board_read=board is not None,
        risks_read=any(s.get("agent") == "A4" for s in steps or []),
        approvals=_approvals(status.get("portfolio_id", ""), in_scope),
        **_board_facts(board or [], in_scope),
    )


def _approvals(scope: str, in_scope: set[str] | None) -> list[ApprovalFact]:
    from ma_pmo.core.hitl import list_pending

    out = []
    for a in list_pending():
        ref = a.get("task_ref") or ""
        project = ref.split("/", 1)[1] if "/" in ref else None
        if not ref.startswith(scope) or (in_scope is not None and project not in in_scope):
            continue
        out.append(ApprovalFact(
            id=f"approval.{a['approval_id']}", approval_id=a["approval_id"], task_ref=ref,
            project_id=project, sender=a["sender"],
            schema_=(a.get("payload") or {}).get("schema", ""),
            requested_at=a["requested_at"], held_by_review=a.get("review") is not None))
    return out


def overall_status(facts: ReportFacts) -> Status:
    worst: Status = max((f.status for f in facts.projects), key=_RANK.__getitem__,
                        default="green")
    if facts.breaches and worst == "green":
        return "amber"
    return worst
