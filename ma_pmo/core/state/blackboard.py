"""Blackboard — the shared portfolio state that supervisor and workers go through.

Agents collaborate through this state store rather than talking directly (loose coupling,
easy auditing). Used as the State of the LangGraph graph.
"""
from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict


class PortfolioState(TypedDict, total=False):
    """LangGraph state. `messages`/`kpi_refs` accumulate node outputs (reducer)."""

    goal: str  # goal the user gave to A1
    task_ref: str  # scope (e.g. PORTFOLIO#2026-Q1)
    gate: str  # gate for A6 to review (e.g. G2-planning)

    # A1 routing result (routing.v1)
    routing: dict[str, Any]

    # worker outputs: agent_id -> payload dict (appended)
    outputs: Annotated[list[dict[str, Any]], operator.add]

    # dict form of exchanged structured messages (§4) (appended)
    messages: Annotated[list[dict[str, Any]], operator.add]

    # final synthesis (A1)
    synthesis: dict[str, Any]

    # HITL: message_ids awaiting approval
    pending_approvals: Annotated[list[str], operator.add]
