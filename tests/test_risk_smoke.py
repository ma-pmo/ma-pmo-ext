"""A4 risk smoke test — mocks the LLM to check the end-to-end logic.

mock status -> signals -> (mocked) rating -> store Risk -> RLT KPI -> high-severity HITL gate.
"""
from __future__ import annotations

from sqlalchemy import select

from ma_pmo.agents.risk import RiskAgent
from ma_pmo.core.schemas.payloads.risk_alert_v1 import RiskAlertV1
from ma_pmo.db.models import Approval, KpiEvent, Risk
from ma_pmo.db.session import get_session


def _fake_alert(system, user, schema, *, agent="?", model=None):
    # pin PROJ-31 (red) to high severity
    return RiskAlertV1(
        project_id="WILL_BE_OVERWRITTEN",
        signal="critical path delay and stalled burndown",
        severity="high",
        lead_time_days=5.0,
        mitigation="add data resources and adjust scope",
        rationale="red status + low progress",
    )


def test_a4_detects_risk_and_gates_high_severity(monkeypatch):
    monkeypatch.setattr("ma_pmo.core.llm.complete_structured", _fake_alert)

    agent = RiskAgent()
    result = agent.run({"task_ref": "PORTFOLIO#2026-Q1"})

    # fixtures include flagged projects such as amber (PROJ-14) and red (PROJ-31)
    assert result["outputs"], "expected risk outputs"
    assert all(o["schema"] == "risk_alert.v1" for o in result["outputs"])

    with get_session() as s:
        risks = s.scalars(select(Risk)).all()
        assert risks, "must be stored in the risk register"

        rlt = s.scalars(
            select(KpiEvent).where(KpiEvent.metric == "risk_lead_time_days")
        ).all()
        assert rlt, "RLT KPI event recorded (H3)"
        # rule-based vs. LLM severity agreement is recorded in meta
        assert "agreement" in rlt[0].meta

        # high severity -> approval queue (HITL)
        gated = s.scalars(select(Approval).where(Approval.decision == "pending")).all()
        assert gated, "high-severity risks must go to the approval gate"


def test_a4_assess_single_project(monkeypatch):
    monkeypatch.setattr("ma_pmo.core.llm.complete_structured", _fake_alert)
    out = RiskAgent().assess_project("PROJ-31")
    assert out is not None and out["risk"]["project_id"] == "PROJ-31"
