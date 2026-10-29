"""A1 Orchestrator — portfolio governance supervisor (§3.2). [operational]

Role: perceive the goal -> decompose and route (routing.v1) -> synthesize worker outputs
-> approval gate. Hierarchical: A1 makes strategic calls, specialist workers (A2–A7) execute.
"""
from __future__ import annotations

import json

import structlog

from ma_pmo.agents.base import BaseAgent
from ma_pmo.agents.orchestrator_rules import deterministic_synthesis, keyword_route
from ma_pmo.core import llm
from ma_pmo.core.i18n import tr
from ma_pmo.core.schemas.payloads.routing_v1 import WORKER_AGENTS, RoutingV1
from ma_pmo.core.state.blackboard import PortfolioState

_log = structlog.get_logger()

_ROLE = f"""You are the PMO orchestrator (supervisor). Given the user's goal, decide which
specialist workers to delegate what to. Available workers:
- A2 Planning (schedule/CPM), A3 Resources (allocation/load), A4 Risk (early detection),
- A5 Reporting (executive reports/Q&A), A6 Governance (gates/quality), A7 Knowledge (RAG)

Select only the minimum set of workers the goal needs. All of A2–A7 are operational.
The goal may be written in English or Korean.
- report / status / executive summary -> A5
- risk / early warning / delay check -> A4
- schedule / critical path / CPM -> A2
- resource / allocation / staffing / load / idle -> A3
- gate / quality / governance / methodology compliance -> A6
- knowledge / lessons learned / similar cases / estimate evidence -> A7
- composite goals delegate to every worker needed (e.g. "executive report incl. risks" -> A4, A5)
Allowed workers: {sorted(WORKER_AGENTS)}"""


class OrchestratorAgent(BaseAgent[RoutingV1]):
    agent_id = "A1"
    function = "Portfolio governance (orchestration)"
    role_prompt = _ROLE
    output_schema = RoutingV1

    def route(self, state: PortfolioState) -> dict:
        """Decompose the goal into a routing decision; rule-based fallback if the LLM fails."""
        goal = state.get("goal", "")
        task_ref = state.get("task_ref", "PORTFOLIO#2026-Q1")
        try:
            decision = self.structured(
                f"Goal: {goal}\nScope: {task_ref}\n\nCreate the delegation plan."
            )
            mode = "llm"
        except Exception as e:  # no key / gateway outage -> deterministic routing
            _log.warning("route_fallback", error=str(e))
            decision = keyword_route(goal)
            mode = "rule"
        # keep only valid workers (guards against hallucinated routing)
        decision.delegations = [d for d in decision.delegations if d.agent in WORKER_AGENTS]
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
            summary = deterministic_synthesis(goal, outputs)
        return {"synthesis": {"summary": summary, "outputs": outputs}}
