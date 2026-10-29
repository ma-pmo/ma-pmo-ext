"""A5 reporting smoke test — mocks the LLM to check the end-to-end logic.

Without a real API: mock status -> (mocked) report generation -> store report -> RCT KPI.
"""
from __future__ import annotations

from sqlalchemy import select

from ma_pmo.agents.reporting import ReportingAgent
from ma_pmo.core.schemas.payloads.report_v1 import ProjectStatusLine, ReportV1
from ma_pmo.db.models import KpiEvent, Report
from ma_pmo.db.session import get_session


def _fake_report(system, user, schema, *, agent="?", model=None):
    return ReportV1(
        scope="PORTFOLIO#2026-Q1",
        executive_summary="1 of 3 projects is red. Watch the data project delay.",
        project_status=[
            ProjectStatusLine(
                project_id="PROJ-31", name="Data", status="red",
                percent_complete=25.0, headline="Schedule delay",
            )
        ],
        key_risks=["PROJ-31 critical path delay"],
        recommended_actions=["Reallocate data resources"],
    )


def test_a5_generates_report_and_records_rct(monkeypatch):
    # mock llm.complete_structured, which base.structured calls
    monkeypatch.setattr("ma_pmo.core.llm.complete_structured", _fake_report)

    agent = ReportingAgent()
    result = agent.run({"goal": "executive report", "task_ref": "PORTFOLIO#2026-Q1"})

    assert result["outputs"][0]["schema"] == "report.v1"

    with get_session() as s:
        reports = s.scalars(select(Report).where(Report.generated_by == "A5")).all()
        assert reports, "report must be stored"
        rct = s.scalars(
            select(KpiEvent).where(KpiEvent.metric == "report_cycle_time_sec")
        ).all()
        assert rct, "RCT KPI event must be recorded (H1)"
