"""Protocol: append-only log + approval queue when gated."""
from __future__ import annotations

from sqlalchemy import select

from ma_pmo.core import protocol
from ma_pmo.core.schemas.message import AgentMessage, Intent, MessagePayload
from ma_pmo.db.models import AgentMessageRow, Approval
from ma_pmo.db.session import get_session


def _gated_message() -> AgentMessage:
    return AgentMessage(
        sender="A5",
        receiver="A1",
        intent=Intent.PROPOSE,
        task_ref="PORTFOLIO#2026-Q1",
        payload=MessagePayload(schema="report.v1", data={
            "scope": "PORTFOLIO#2026-Q1", "executive_summary": "draft", "project_status": [],
        }),
        confidence=0.5,
        human_gate_required=True,
    )


def test_publish_writes_immutable_log_and_queues_approval():
    msg = protocol.publish(_gated_message())
    with get_session() as s:
        row = s.get(AgentMessageRow, msg.message_id)
        assert row is not None and row.sender == "A5"
        approval = s.scalar(
            select(Approval).where(Approval.message_id == msg.message_id)
        )
        assert approval is not None and approval.decision == "pending"
