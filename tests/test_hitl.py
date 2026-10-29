"""HITL: approval handling + approval-latency KPI."""
from __future__ import annotations

from sqlalchemy import select

from ma_pmo.core import hitl, protocol
from ma_pmo.core.schemas.message import AgentMessage, Intent, MessagePayload
from ma_pmo.db.models import KpiEvent
from ma_pmo.db.session import get_session


def test_resolve_approval_records_latency_kpi():
    msg = protocol.publish(
        AgentMessage(
            sender="A5", receiver="A1", intent=Intent.PROPOSE, task_ref="PORTFOLIO#2026-Q1",
            payload=MessagePayload(schema="report.v1", data={
                "scope": "PORTFOLIO#2026-Q1", "executive_summary": "draft", "project_status": [],
            }),
            confidence=0.5, human_gate_required=True,
        )
    )
    pending = [p for p in hitl.list_pending() if p["message_id"] == msg.message_id]
    assert pending, "must be queued for approval"

    result = hitl.resolve(pending[0]["approval_id"], approver="tester", decision="approve")
    assert result["decision"] == "approve"

    with get_session() as s:
        events = s.scalars(
            select(KpiEvent).where(KpiEvent.metric == "approval_latency_sec")
        ).all()
    assert any(e.meta.get("message_id") == msg.message_id for e in events)
