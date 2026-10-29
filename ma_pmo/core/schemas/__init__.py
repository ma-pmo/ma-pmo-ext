"""Structured message and payload schemas (Pydantic v2, `.v1` versioning enforced)."""
from ma_pmo.core.schemas.message import AgentMessage, Intent, MessagePayload

__all__ = ["AgentMessage", "Intent", "MessagePayload"]
