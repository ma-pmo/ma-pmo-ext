"""Public SDK for agent plugins — the only semver-stable surface of MA-PMO.

Import from here, never from other `ma_pmo` modules: everything else may change between
releases. A breaking change to this module raises `SDK_VERSION`. Guide: docs/PLUGINS.md.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from ma_pmo.agents.base import BaseAgent
from ma_pmo.agents.registry import AgentSpec
from ma_pmo.core import protocol
from ma_pmo.core.i18n import tr
from ma_pmo.core.kpi import Axis
from ma_pmo.core.kpi import record as record_kpi
from ma_pmo.core.schemas.message import AgentMessage, Intent, MessagePayload
from ma_pmo.core.state.blackboard import PortfolioState
from ma_pmo.integrations.registry import get_tracker

SDK_VERSION = "1"


def publish(agent: BaseAgent[Any], schema: str, data: BaseModel, *, task_ref: str,
            confidence: float = 0.9, needs_approval: bool = False) -> dict:
    """Publish one output through the audited message log; returns the entry for `outputs`.

    `needs_approval=True` sends it to a person, as does a confidence below the HITL threshold.
    """
    payload = data.model_dump(mode="json")
    protocol.publish(AgentMessage(
        sender=agent.agent_id,
        receiver="A1",
        intent=Intent.PROPOSE if needs_approval else Intent.INFORM,
        task_ref=task_ref,
        payload=MessagePayload(schema_=schema, data=payload),
        confidence=confidence,
        human_gate_required=needs_approval,
    ))
    return {"agent": agent.agent_id, "schema": schema, "data": payload}


__all__ = [
    "SDK_VERSION", "AgentSpec", "Axis", "BaseAgent", "PortfolioState", "get_tracker", "publish",
    "record_kpi", "tr",
]
