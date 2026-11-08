"""A1 Orchestrator — portfolio governance supervisor (§3.2). [operational]

Role: perceive the goal -> decompose and route (routing.v1) -> synthesize worker outputs
-> approval gate. Hierarchical: A1 makes strategic calls, specialist workers (A2–A7) execute.
"""
from __future__ import annotations

import json

import structlog

from ma_pmo.agents import registry
from ma_pmo.agents.base import BaseAgent
from ma_pmo.agents.orchestrator_rules import deterministic_synthesis, keyword_route
from ma_pmo.core import llm, tracing
from ma_pmo.core.i18n import tr
from ma_pmo.core.schemas.payloads.routing_v1 import RoutingV1
from ma_pmo.core.scope import DEFAULT_SCOPE
from ma_pmo.core.state.blackboard import PortfolioState

_log = structlog.get_logger()

def _role_prompt() -> str:
    specs = registry.routable()
    workers = "\n".join(f"- {spec.id} {spec.capability}" for spec in specs.values())
    return f"""You are the PMO orchestrator (supervisor). Given the user's goal, decide which
specialist workers to delegate what to. Available workers, with what each one is for:
{workers}

Select only the minimum set of workers the goal needs. All listed workers are operational.
The goal may be written in English or Korean.
Composite goals delegate to every worker needed (e.g. "executive report incl. risks" -> A4, A5).
Allowed workers: {sorted(specs)}"""


class OrchestratorAgent(BaseAgent[RoutingV1]):
    agent_id = "A1"
    function = "Portfolio governance (orchestration)"
    output_schema = RoutingV1

    def __init__(self) -> None:
        self.role_prompt = _role_prompt()

    def route(self, state: PortfolioState) -> dict:
        """Decompose the goal into a routing decision; rule-based fallback if the LLM fails."""
        goal = state.get("goal", "")
        task_ref = state.get("task_ref", DEFAULT_SCOPE)
        try:
            decision = self.structured(
                f"Goal: {goal}\nScope: {task_ref}\n\nCreate the delegation plan."
            )
            mode = "llm"
        except Exception as e:  # no key / gateway outage -> deterministic routing
            _log.warning("route_fallback", error=str(e))
            tracing.mark_fallback("A1 routing", e)
            decision = keyword_route(goal)
            mode = "rule"
        # keep only valid workers (guards against hallucinated routing)
        decision.delegations = [d for d in decision.delegations if d.agent in registry.routable()]
        if not decision.delegations:  # backfill with rules if the LLM returned no delegations
            decision = keyword_route(goal)
            mode = "rule"
        routing = decision.model_dump()
        routing["mode"] = mode
        return {"routing": routing}

    def synthesize(self, state: PortfolioState) -> dict:
        """Synthesize worker outputs for executives; rule-based fallback if the LLM fails."""
        outputs = state.get("outputs", [])
        goal = state.get("goal", "")
        if not outputs:
            return {
                "synthesis": {
                    "summary": tr("No worker outputs.", "작업자 산출물이 없습니다."),
                    "outputs": [],
                }
            }
        try:
            summary = llm.complete(
                "You are the PMO orchestrator. Synthesize the worker outputs into one "
                "paragraph for executives.",
                f"Goal: {goal}\nOutputs (JSON):\n"
                f"{json.dumps(outputs, ensure_ascii=False, indent=2)}",
                agent=self.agent_id,
            )
        except Exception as e:
            _log.warning("synthesize_fallback", error=str(e))
            tracing.mark_fallback("A1 synthesis", e)
            summary = deterministic_synthesis(goal, outputs)
        return {"synthesis": {"summary": summary, "outputs": outputs}}
