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
