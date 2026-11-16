"""§4 message and payload schema validation."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from ma_pmo.core.schemas.message import AgentMessage, Intent, MessagePayload
from ma_pmo.core.schemas.payloads import PAYLOAD_REGISTRY
from ma_pmo.core.schemas.payloads.report_v1 import ReportV1


def test_payload_requires_version():
    with pytest.raises(ValidationError):
        MessagePayload(schema="report", data={})  # missing version -> rejected


def test_message_gate_by_confidence():
    msg = AgentMessage(
        sender="A4",
        receiver="A1",
        intent=Intent.PROPOSE,
        task_ref="PORTFOLIO#2026-Q1",
        payload=MessagePayload(schema="risk_alert.v1", data={
            "project_id": "PROJ-14", "signal": "delay", "severity": "high",
            "mitigation": "reallocate",
            "rationale": "stalled burndown",
        }),
        confidence=0.4,
    )
    assert msg.needs_human_gate(confidence_threshold=0.6) is True
    assert msg.needs_human_gate(confidence_threshold=0.3) is False


def test_registry_covers_report():
    assert PAYLOAD_REGISTRY["report.v1"] is ReportV1


@pytest.mark.parametrize("severity", ["High", "높음", "somewhere in the middle", ""])
def test_risk_severity_is_a_closed_set(severity):
    """Every reader compares severity with sets like {"high", "critical"}: another spelling would
    pass validation and silently skip the approval gate, notifications and review."""
    from ma_pmo.core.schemas.payloads.risk_alert_v1 import RiskAlertV1

    with pytest.raises(ValidationError):
        RiskAlertV1(project_id="P", signal="s", severity=severity, mitigation="m", rationale="r")


def test_gate_decision_and_report_status_are_closed_sets():
    from ma_pmo.core.schemas.payloads.gate_review_v1 import GateReviewV1
    from ma_pmo.core.schemas.payloads.report_v1 import ProjectStatusLine

    with pytest.raises(ValidationError):
        GateReviewV1(project_id="P", gate="G2-planning", decision="Pass")
    with pytest.raises(ValidationError):
        ProjectStatusLine(project_id="P", name="P", status="yellow", percent_complete=1,
                          headline="h")
    # the LLM is given the JSON schema, so it sees the allowed values too
    schema = PAYLOAD_REGISTRY["risk_alert.v1"].model_json_schema()
    assert schema["properties"]["severity"]["enum"] == ["low", "medium", "high", "critical"]
