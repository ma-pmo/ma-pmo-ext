"""LangGraph supervisor graph — the supervisor–worker pattern of paper §2.2.

A1 (route) -> fan out to delegated workers -> A1 (synthesize) -> END.
Agents collaborate through shared state (PortfolioState), checkpointed with SqliteSaver
(audit and resume).

HITL: compiling with `interrupt_before_synthesis=True` pauses the graph right before
synthesis for human approval (high-risk decision gate). Defaults to False (reporting is
low risk).
"""
from __future__ import annotations

from typing import Any

from langgraph.graph import END, StateGraph

from ma_pmo.agents.base import BaseAgent
from ma_pmo.agents.governance import GovernanceAgent
from ma_pmo.agents.knowledge import KnowledgeAgent
from ma_pmo.agents.orchestrator import OrchestratorAgent
from ma_pmo.agents.planning import PlanningAgent
from ma_pmo.agents.reporting import ReportingAgent
from ma_pmo.agents.resource import ResourceAgent
from ma_pmo.agents.risk import RiskAgent
from ma_pmo.core.state.blackboard import PortfolioState
from ma_pmo.core.state.checkpointer import build_checkpointer

_orchestrator = OrchestratorAgent()

# worker node registry (id -> agent)
WORKERS: dict[str, BaseAgent[Any]] = {
    "A2": PlanningAgent(),
    "A3": ResourceAgent(),
    "A4": RiskAgent(),
    "A5": ReportingAgent(),
    "A6": GovernanceAgent(),
    "A7": KnowledgeAgent(),
}


def _route(state: PortfolioState) -> dict:
    return _orchestrator.route(state)


def _dispatch(state: PortfolioState) -> list[str]:
    """Routing decision -> worker nodes to run (fan-out); straight to synthesis if none."""
    dels = state.get("routing", {}).get("delegations", [])
    targets = [d["agent"] for d in dels if d["agent"] in WORKERS]
    return targets or ["synthesize"]


def _synthesize(state: PortfolioState) -> dict:
    return _orchestrator.synthesize(state)


def build_graph(*, interrupt_before_synthesis: bool = False):
    """Compile and return the supervisor graph."""
    g = StateGraph(PortfolioState)

    g.add_node("route", _route)
    for wid, agent in WORKERS.items():
        g.add_node(wid, agent.run)
    g.add_node("synthesize", _synthesize)

    g.set_entry_point("route")
    # route -> (fan-out) workers or synthesize
    g.add_conditional_edges("route", _dispatch, [*WORKERS.keys(), "synthesize"])
    # each worker -> synthesize (fan-in); outputs accumulate via the operator.add reducer
    for wid in WORKERS:
        g.add_edge(wid, "synthesize")
    g.add_edge("synthesize", END)

    checkpointer = build_checkpointer()
    interrupt_before = ["synthesize"] if interrupt_before_synthesis else None
    return g.compile(checkpointer=checkpointer, interrupt_before=interrupt_before)
