"""A3 Resource agent — allocation/load (§3.2). [operational]

Flow: mock status + resource master -> greedy allocation (deterministic) -> allocation.v1
      -> store Allocation -> utilization/idle KPIs (resource axis, H2) -> overload alerts
      -> message to A1 (overload sets human_gate_required -> reallocation approval).
"""
from __future__ import annotations

from sqlalchemy import delete, select

from ma_pmo.agents.allocation import allocate
from ma_pmo.agents.base import BaseAgent
from ma_pmo.connectors.jira_mock import MockJiraConnector
from ma_pmo.core import kpi, protocol
from ma_pmo.core.kpi import Axis
from ma_pmo.core.schemas.message import AgentMessage, Intent, MessagePayload
from ma_pmo.core.schemas.payloads.allocation_v1 import AllocationLine, AllocationV1
from ma_pmo.core.state.blackboard import PortfolioState
from ma_pmo.db.models import Allocation, Resource
from ma_pmo.db.session import get_session

_ROLE = """You are the PMO resource agent. Allocate resources by skill match and flag overloads."""


class ResourceAgent(BaseAgent[AllocationV1]):
    agent_id = "A3"
    function = "Resources (allocation/load)"
    role_prompt = _ROLE
    output_schema = AllocationV1

    def __init__(self, tracker: MockJiraConnector | None = None) -> None:
        self.tracker = tracker or MockJiraConnector()

    def _resources(self) -> list[dict]:
        with get_session() as s:
            return [
                {"id": r.id, "skill": r.skill, "capacity": r.capacity}
                for r in s.scalars(select(Resource)).all()
            ]

    def run(self, state: PortfolioState) -> dict:
        scope = state.get("task_ref", "PORTFOLIO#2026-Q1")
        alloc, msg = self._allocate(scope)
        return {
            "outputs": [
                {"agent": self.agent_id, "schema": "allocation.v1", "data": alloc.model_dump()}
            ],
            "messages": [msg.model_dump(by_alias=True, mode="json")],
        }

    def allocate_portfolio(self, scope: str = "PORTFOLIO#2026-Q1") -> dict:
        alloc, _ = self._allocate(scope)
        return alloc.model_dump()

    def _allocate(self, scope: str) -> tuple[AllocationV1, AgentMessage]:
        status = self.tracker.get_portfolio_status(scope)
        projects = status.get("projects", [])
        result = allocate(projects, self._resources())

        alloc = AllocationV1(
            plan=[
                AllocationLine(
                    project_id=ln.project_id,
                    resource_id=ln.resource_id,
                    week=ln.week,
                    hours=ln.hours,
                )
                for ln in result.lines
            ],
            overload_alerts=result.overload_alerts,
            utilization_pct=result.utilization_pct,
        )

        # persist allocation (replaces previous allocation -> reflects reallocation)
        with get_session() as s:
            s.execute(delete(Allocation))
            for ln in result.lines:
                s.add(
                    Allocation(
                        project_id=ln.project_id,
                        resource_id=ln.resource_id,
                        week=ln.week,
                        hours=ln.hours,
                    )
                )

        # resource-axis KPIs (H2): utilization, idle rate
        kpi.record(Axis.RESOURCE, "utilization_pct", result.utilization_pct)
        kpi.record(Axis.RESOURCE, "idle_pct", result.idle_pct)

        gate = bool(result.overload_alerts)  # overload -> reallocation needs human approval
        msg = AgentMessage(
            sender=self.agent_id,
            receiver="A1",
            intent=Intent.PROPOSE if gate else Intent.INFORM,
            task_ref=scope,
            payload=MessagePayload(schema_="allocation.v1", data=alloc.model_dump()),
            confidence=0.9,
            human_gate_required=gate,
        )
        protocol.publish(msg)
        return alloc, msg
