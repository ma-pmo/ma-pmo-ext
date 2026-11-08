"""Structured message protocol — paper §4.

Schema-based messages instead of free-form chat curb error propagation and hallucination
and leave an audit trail. Every payload must carry a versioned `schema` (`.v1`) to limit
error propagation in long-running workflows.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class Intent(str, Enum):
    REQUEST = "request"
    INFORM = "inform"
    PROPOSE = "propose"
    APPROVE = "approve"


class MessagePayload(BaseModel):
    """Versioned payload envelope. `schema` has the form `<name>.vN`."""

    schema_: str = Field(alias="schema", description="e.g. risk_alert.v1, report.v1")
    data: dict[str, Any]

    model_config = {"populate_by_name": True}

    @field_validator("schema_")
    @classmethod
    def _require_version(cls, v: str) -> str:
        if ".v" not in v:
            raise ValueError(f"payload schema must include a version (e.g. report.v1), got={v!r}")
        return v


class EvidenceRef(BaseModel):
    """What a message rests on: another message, a tracker field or a knowledge entry.

    `{"kind": "message", "ref": "<message_id>"}`, `{"kind": "tracker", "ref": "PROJ-14",
    "field": "planned_finish"}`, `{"kind": "knowledge", "ref": "<lesson id>"}`. Reviews cite
    these instead of restating them, so a person can follow a verdict back to its source.
    """

    kind: Literal["message", "tracker", "knowledge"]
    ref: str = Field(min_length=1)
    field: str | None = None


def _now() -> datetime:
    return datetime.now(UTC)


class AgentMessage(BaseModel):
    """Immutable (append-only) message between agents. Paper §4 schema."""

    message_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    sender: str  # e.g. "A4"
    receiver: str  # e.g. "A1"
    intent: Intent
    task_ref: str  # e.g. "PORTFOLIO#2026-Q1/PROJ-14"
    payload: MessagePayload
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    human_gate_required: bool = False
    evidence: list[EvidenceRef] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=_now)

    def needs_human_gate(self, confidence_threshold: float) -> bool:
        """Approval is needed if a gate is explicitly required or confidence is too low."""
        return self.human_gate_required or self.confidence < confidence_threshold
