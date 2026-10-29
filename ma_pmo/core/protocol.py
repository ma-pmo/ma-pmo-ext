"""Message bus · routing · append-only log — paper §4.

Every §4 message is stored in an immutable log (agent_message table) for auditability and
reproducibility. Payloads are validated against the schema registry to curb error propagation.
"""
from __future__ import annotations

from ma_pmo.core.config import get_settings
from ma_pmo.core.obs import get_logger
from ma_pmo.core.schemas.message import AgentMessage
from ma_pmo.core.schemas.payloads import PAYLOAD_REGISTRY
from ma_pmo.db.models import AgentMessageRow, Approval
from ma_pmo.db.session import get_session

_settings = get_settings()
_log = get_logger("protocol")


def validate_payload(message: AgentMessage) -> None:
    """Validate with the registered Pydantic model if payload.schema is in the registry."""
    schema = message.payload.schema_
    model = PAYLOAD_REGISTRY.get(schema)
    if model is not None:
        model.model_validate(message.payload.data)  # raises ValidationError on violation


def publish(message: AgentMessage) -> AgentMessage:
    """Validate the message and append it to the immutable log; queue it for approval if gated.

    The returned message is stored append-only; its later state is tracked via approval.
    """
    validate_payload(message)
    with get_session() as s:
        s.add(
            AgentMessageRow(
                message_id=message.message_id,
                sender=message.sender,
                receiver=message.receiver,
                intent=message.intent.value,
                task_ref=message.task_ref,
                payload=message.payload.model_dump(by_alias=True),
                confidence=message.confidence,
                human_gate_required=message.human_gate_required,
                timestamp=message.timestamp,
            )
        )
        gated = message.needs_human_gate(_settings.hitl_confidence_threshold)
        if gated:
            s.add(Approval(message_id=message.message_id, decision="pending"))
    # behavior log: structured message published (§4 audit trail)
    _log.info(
        "message",
        frm=message.sender,
        to=message.receiver,
        intent=message.intent.value,
        schema=message.payload.schema_,
        task_ref=message.task_ref,
        confidence=message.confidence,
        gated=gated,
    )
    return message
