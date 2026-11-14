"""A3 Resource agent — allocation/load (§3.2). [operational]

Flow: mock status + resource master -> greedy allocation (deterministic) -> allocation.v1
      -> store Allocation -> utilization/idle KPIs (resource axis, H2) -> overload alerts
      -> message to A1 (overload sets human_gate_required -> reallocation approval).
"""
from __future__ import annotations

from collections.abc import Callable

from sqlalchemy import ColumnElement, delete, func, or_, select

from ma_pmo.agents import common
from ma_pmo.agents.allocation import allocate
from ma_pmo.agents.base import BaseAgent
from ma_pmo.connectors.base import IssueTrackerConnector
from ma_pmo.connectors.calendar import CalendarConnector, get_calendar
from ma_pmo.core import kpi, protocol
from ma_pmo.core.kpi import Axis
from ma_pmo.core.schemas.message import AgentMessage, Intent, MessagePayload
from ma_pmo.core.schemas.payloads.allocation_v1 import AllocationLine, AllocationV1
from ma_pmo.core.scope import DEFAULT_SCOPE
from ma_pmo.core.state.blackboard import PortfolioState
from ma_pmo.db.models import Allocation, Project, Resource
from ma_pmo.db.session import get_session
from ma_pmo.integrations.registry import get_tracker

_ROLE = """You are the PMO resource agent. Allocate resources by skill match and flag overloads."""


def _in_scope(scope: str, projects: list[dict]) -> ColumnElement[bool]:
    """Allocations of this portfolio: the tracker's projects and any stored under it."""
    return or_(
        Allocation.project_id.in_([p["project_id"] for p in projects]),
        Allocation.project_id.in_(select(Project.id).where(Project.portfolio_id == scope)),
    )


class ResourceAgent(BaseAgent[AllocationV1]):
    agent_id = "A3"
    function = "Resources (allocation/load)"
    role_prompt = _ROLE
    output_schema = AllocationV1

    def __init__(self, tracker: IssueTrackerConnector | None = None,
                 calendar: CalendarConnector | None = None) -> None:
        self.tracker = tracker or get_tracker()
        self.calendar = calendar if calendar is not None else get_calendar()

    def _resources(self) -> list[dict]:
        with get_session() as s:
            return [
                {"id": r.id, "skill": r.skill, "capacity": r.capacity}
                for r in s.scalars(select(Resource)).all()
            ]

    def _busy(self, scope: str, projects: list[dict]) -> Callable[[str, str], float]:
        """Hours a person cannot give this portfolio: calendar plus other portfolios' plans."""
        with get_session() as s:
            booked = {
                (resource_id, week): hours
                for resource_id, week, hours in s.execute(
                    select(Allocation.resource_id, Allocation.week, func.sum(Allocation.hours))
                    .where(~_in_scope(scope, projects))
                    .group_by(Allocation.resource_id, Allocation.week)
                )
            }
        calendar = self.calendar

        def busy(resource_id: str, week: str) -> float:
            held = calendar.busy_hours(resource_id, week) if calendar is not None else 0.0
            return held + booked.get((resource_id, week), 0.0)

        return busy

    def run(self, state: PortfolioState) -> dict:
        scope = state.get("task_ref", DEFAULT_SCOPE)
        alloc, msg = self._allocate(scope)
        return {
            "outputs": [common.entry(self.agent_id, "allocation.v1", alloc)],
            "messages": [common.wire(msg)],
        }

    def allocate_portfolio(self, scope: str = DEFAULT_SCOPE) -> dict:
        alloc, _ = self._allocate(scope)
        return alloc.model_dump()

    def _allocate(self, scope: str) -> tuple[AllocationV1, AgentMessage]:
        status = self.tracker.get_portfolio_status(scope)
        projects = status.get("projects", [])
        result = allocate(projects, self._resources(), busy=self._busy(scope, projects),
                          start=status.get("plan_start"))

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
            unstaffed=result.unstaffed,
        )

        # persist allocation (replaces this portfolio's plan -> reflects reallocation)
        with get_session() as s:
            s.execute(delete(Allocation).where(_in_scope(scope, projects)))
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
