"""Message bus · routing · append-only log — paper §4.

Every §4 message is stored in an immutable log (agent_message table) for auditability and
reproducibility. Payloads are validated against the schema registry to curb error propagation.
"""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select

from ma_pmo.core import risk_control
from ma_pmo.core.config import get_settings
from ma_pmo.core.obs import get_logger
from ma_pmo.core.runs import current_run_id, dedupe_key
from ma_pmo.core.schemas.message import AgentMessage
from ma_pmo.core.schemas.payloads import PAYLOAD_REGISTRY
from ma_pmo.core.times import iso
from ma_pmo.db.models import AgentMessageRow, Approval
from ma_pmo.db.session import get_session
from ma_pmo.integrations.dispatch import emit_later
from ma_pmo.integrations.events import events_from_message

_settings = get_settings()
_log = get_logger("protocol")


def validate_payload(message: AgentMessage) -> None:
    """Validate with the registered Pydantic model if payload.schema is in the registry.

    This is the `schema` guardrail (core/guardrails.py, point `output`), enforced by default:
    an invalid payload raises ValidationError. In observe mode it is logged and let through.
    """
    from ma_pmo.core import guardrails

    result = guardrails.run("schema", {"message": message}, message_id=message.message_id)
    if result.decision == guardrails.BLOCK and result.error is not None:
        raise result.error


def _check_schema(context: dict[str, Any], params: dict[str, Any]) -> Any:
    from pydantic import ValidationError

    from ma_pmo.core.guardrails import ALLOW, BLOCK, Result

    message = context["message"]
    schema = message.payload.schema_
    model = PAYLOAD_REGISTRY.get(schema)
    if model is None:
        return Result(ALLOW, f"{schema}: no registered schema", detail={"schema": schema})
    try:
        model.model_validate(message.payload.data)
    except ValidationError as e:
        return Result(BLOCK, f"{schema}: {e.error_count()} invalid field(s)", error=e,
                      detail={"schema": schema, "errors": [
                          {"loc": list(err["loc"]), "msg": err["msg"]} for err in e.errors()]})
    return Result(ALLOW, f"{schema}: valid", detail={"schema": schema})


def _register() -> None:
    from ma_pmo.core.guardrails import ENFORCE, register

    register("schema", "output", ENFORCE,
             "Reject agent payloads that do not match their registered schema")(_check_schema)


_register()


def _exception(message: AgentMessage) -> dict | None:
    """A tolerance breach the output forecasts (roadmap 10): the approval's reason, or None."""
    from ma_pmo.core import guardrails, tolerances

    if message.payload.schema_ not in tolerances.CHECKED:
        return None
    result = guardrails.run("tolerance", {"message": message}, message_id=message.message_id)
    if result.decision != guardrails.ASK:
        return None
    return {"kind": "exception", "breaches": result.detail.get("breaches", []),
            "reason": result.reason}


def publish(message: AgentMessage) -> AgentMessage:
    """Validate the message and append it to the immutable log; queue it for approval if gated.

    The returned message is stored append-only; its later state is tracked via approval.
    """
    validate_payload(message)
    if message.conversation_id is None:  # a run is one conversation; outside one, a new one
        message = message.model_copy(update={
            "conversation_id": current_run_id() or f"conv-{uuid.uuid4().hex[:12]}"})
    exception = _exception(message)
    key = dedupe_key("message")
    with get_session() as s:
        stored = s.scalar(select(AgentMessageRow.message_id).where(
            AgentMessageRow.dedupe_key == key)) if key else None
        if stored:  # a retried step already published this: answer with the stored id
            return message.model_copy(update={"message_id": stored})
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
                evidence=[e.model_dump(exclude_none=True) for e in message.evidence],
                timestamp=message.timestamp,
                run_id=current_run_id(),
                dedupe_key=key,
                conversation_id=message.conversation_id,
                in_reply_to=message.in_reply_to,
                reply_by=message.reply_by,
            )
        )
        gated = message.needs_human_gate(
            risk_control.threshold_for(message.sender, _settings.hitl_confidence_threshold)
        ) or exception is not None
        if gated:
            # no reason at all (SQL NULL) unless there is one: JSON null would read as a reason
            s.add(Approval(message_id=message.message_id, decision="pending",
                           run_id=current_run_id(), **({"reason": exception} if exception else {})))
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
    # notify integrations (Slack, webhooks, ...) in the background: best effort, never raises,
    # and a slow webhook does not hold the run
    emit_later(events_from_message(message, gated, exception))
    return message


def message_dict(row: AgentMessageRow, *, payload: bool = True) -> dict:
    """A logged message as the API lists it; `payload=False` leaves the payload out."""
    item = {
        "message_id": row.message_id,
        "sender": row.sender,
        "receiver": row.receiver,
        "intent": row.intent,
        "schema": row.payload.get("schema") if isinstance(row.payload, dict) else None,
        "task_ref": row.task_ref,
        "confidence": row.confidence,
        "human_gate_required": row.human_gate_required,
    }
    if payload:
        item["payload"] = row.payload
    item["timestamp"] = iso(row.timestamp)
    item["conversation_id"] = row.conversation_id
    item["in_reply_to"] = row.in_reply_to
    item["reply_by"] = iso(row.reply_by)
    return item
