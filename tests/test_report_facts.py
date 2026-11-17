"""Roadmap 12, step 1: the facts under A5's report and the stored report.v2."""
from __future__ import annotations

from datetime import date

from sqlalchemy import select

from ma_pmo.agents.reporting import ReportingAgent
from ma_pmo.core.schemas.payloads import PAYLOAD_REGISTRY
from ma_pmo.core.schemas.payloads.report_v2 import ReportV2
from ma_pmo.db.models import Report
from ma_pmo.db.session import get_session
from ma_pmo.reports import facts

TODAY = date(2026, 2, 1)


def task(tid, effort, pct, deps=()):
    return {"task_id": tid, "wbs": tid, "effort": effort, "percent_complete": pct,
            "deps": list(deps)}


def portfolio(*projects):
    return {"portfolio_id": "P", "found": True, "projects": list(projects)}


ON_TRACK = {"project_id": "A", "status": "green", "percent_complete": 50.0,
            "planned_start": "2026-01-05", "deadline": "2026-03-31",
            "tasks": [task("A1", 40, 100), task("A2", 40, 0, ["A1"])]}
LATE = {"project_id": "B", "status": "amber", "percent_complete": 10.0,
        "planned_start": "2026-01-05", "deadline": "2026-01-20",
        "tasks": [task("B1", 80, 10), task("B2", 80, 10, ["B1"])]}


def kpis(f):
    return {k.id: k for k in f.kpis}


def test_facts_without_a_previous_report():
    f = facts.build(portfolio(ON_TRACK, LATE), today=TODAY)
    k = kpis(f)
    assert f.as_of == "2026-02-01" and f.period_start is None and f.previous_report_id is None
    assert k["kpi.progress"].value == 30.0
    assert k["kpi.spi"].value == round((40 + 16) / 240, 3)
    assert (k["kpi.amber"].value, k["kpi.red"].value, k["kpi.late"].value) == (1, 0, 1)
    assert all(x.previous is None and x.delta is None for x in f.kpis)
    b = next(p for p in f.projects if p.project_id == "B")
    assert b.forecast_finish and b.slack_days is not None and b.slack_days < 0
    assert k["kpi.worst_slack"].value == b.slack_days


def test_tolerances_and_overall_status(monkeypatch):
    f = facts.build(portfolio(ON_TRACK, LATE), today=TODAY)
    breached = {(t.project_id, t.dimension) for t in f.breaches}
    assert breached == {("B", "schedule"), ("B", "spi"), ("A", "spi")}  # A: SPI 0.5
    assert facts.overall_status(f) == "amber"
    green_late = {**LATE, "status": "green"}
    assert facts.overall_status(facts.build(portfolio(green_late), today=TODAY)) == "amber"
    red = {**ON_TRACK, "status": "red"}
    assert facts.overall_status(facts.build(portfolio(red), today=TODAY)) == "red"

    from ma_pmo.core.config import get_settings
    monkeypatch.setattr(get_settings(), "tolerance_spi", 0.1)
    monkeypatch.setattr(get_settings(), "tolerance_slip_days", 365)
    relaxed = facts.build(portfolio(ON_TRACK, {**LATE, "status": "green"}), today=TODAY)
    assert relaxed.breaches == [] and facts.overall_status(relaxed) == "green"


def test_compared_with_the_previous_report():
    first = facts.build(portfolio(ON_TRACK, LATE), today=TODAY)
    stored = ReportV2(scope="P", path="rule", overall_status="amber", facts=first,
                      executive_summary="x", project_status=[]).model_dump()
    stored["project_status"] = [{"project_id": "B", "status": "green", "percent_complete": 5.0}]
    moved = {**LATE, "status": "red", "percent_complete": 20.0}
    f = facts.build(portfolio(ON_TRACK, moved), ("RPT-1", "2026-01-25", stored),
                    today=TODAY)
    assert (f.previous_report_id, f.period_start) == ("RPT-1", "2026-01-25")
    k = kpis(f)
    assert (k["kpi.red"].previous, k["kpi.red"].value, k["kpi.red"].delta) == (0, 1, 1)
    assert k["kpi.progress"].delta == 5.0
    b = next(p for p in f.projects if p.project_id == "B")
    assert (b.previous_status, b.previous_percent_complete) == ("green", 5.0)
    a = next(p for p in f.projects if p.project_id == "A")
    assert a.previous_status is None  # not in the previous report


def test_a_report_v1_row_still_gives_previous_project_lines():
    v1 = {"scope": "P", "executive_summary": "x", "key_risks": [], "recommended_actions": [],
          "project_status": [{"project_id": "A", "name": "A", "status": "amber",
                              "percent_complete": 40.0, "headline": ""}]}
    f = facts.build(portfolio(ON_TRACK), ("RPT-0", "2026-01-01", v1), today=TODAY)
    assert f.projects[0].previous_status == "amber"
    assert all(k.previous is None for k in f.kpis)


def test_a5_stores_report_v2_and_compares_with_its_last_report():
    scope = "PORTFOLIO#2026-Q1"
    assert PAYLOAD_REGISTRY["report.v2"] is ReportV2
    agent = ReportingAgent()
    first = agent.run({"goal": "report", "task_ref": scope})
    second = agent.run({"goal": "report", "task_ref": scope})
    assert second["outputs"][0]["schema"] == "report.v1"  # what other agents read is unchanged
    assert first["outputs"][0]["data"] == second["outputs"][0]["data"]
    with get_session() as s:
        rows = s.scalars(select(Report).where(Report.scope == scope)
                         .order_by(Report.created_at.desc())).all()
    latest, before = ReportV2.model_validate(rows[0].content), rows[1]
    assert latest.path == "rule"  # no LLM in tests
    assert latest.facts.previous_report_id == before.id
    assert latest.facts.projects and latest.facts.kpis
    assert all(k.previous == k.value for k in latest.facts.kpis)  # nothing changed in between
    assert latest.to_v1().model_dump() == second["outputs"][0]["data"]
