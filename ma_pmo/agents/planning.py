"""A2 Planning agent — schedule (CPM) (§3.2). [operational]

Flow: collect mock status -> CPM critical path (deterministic, no LLM) -> schedule.v1 ->
      delivery KPIs (SPI=EV/PV, projected slippage) -> inform message to A1.
"""
from __future__ import annotations

from ma_pmo.agents.base import BaseAgent
from ma_pmo.agents.cpm import CpmResult, compute_cpm
from ma_pmo.connectors.jira_mock import MockJiraConnector
from ma_pmo.core import kpi, protocol
from ma_pmo.core.kpi import Axis
from ma_pmo.core.schemas.message import AgentMessage, Intent, MessagePayload
from ma_pmo.core.schemas.payloads.schedule_v1 import ScheduledTask, ScheduleV1
from ma_pmo.core.state.blackboard import PortfolioState

_ROLE = """You are the PMO planning agent. Compute the CPM critical path."""


def _spi(project: dict) -> float | None:
    """SPI = EV/PV (schedule performance index).

    PV = total effort, EV = completion-weighted effort.
    """
    tasks = project.get("tasks", [])
    pv = sum(t.get("effort", 0.0) for t in tasks)
    if pv <= 0:
        return None
    ev = sum(t.get("effort", 0.0) * (t.get("percent_complete", 0.0) / 100.0) for t in tasks)
    return round(ev / pv, 3)


def _slippage_days(project: dict, cpm: CpmResult) -> int | None:
    """Projected slippage = deadline − projected finish (negative means late)."""
    pf = cpm.projected_finish(project.get("planned_start"))
    dl = project.get("deadline")
    if not pf or not dl:
        return None
    from datetime import datetime

    try:
        pf_d = datetime.strptime(pf, "%Y-%m-%d").date()
        dl_d = datetime.strptime(dl, "%Y-%m-%d").date()
    except ValueError:
        return None
    return (dl_d - pf_d).days


class PlanningAgent(BaseAgent[ScheduleV1]):
    agent_id = "A2"
    function = "Planning (schedule/CPM)"
    role_prompt = _ROLE
    output_schema = ScheduleV1

    def __init__(self, tracker: MockJiraConnector | None = None) -> None:
        self.tracker = tracker or MockJiraConnector()

    def run(self, state: PortfolioState) -> dict:
        scope = state.get("task_ref", "PORTFOLIO#2026-Q1")
        status = self.tracker.get_portfolio_status(scope)
        outputs, messages = [], []
        for proj in status.get("projects", []):
            sched, msg = self._plan(proj, scope)
            outputs.append(
                {"agent": self.agent_id, "schema": "schedule.v1", "data": sched.model_dump()}
            )
            messages.append(msg.model_dump(by_alias=True, mode="json"))
        return {"outputs": outputs, "messages": messages}

    def plan_project(self, project_id: str, scope: str = "PORTFOLIO#2026-Q1") -> dict | None:
        status = self.tracker.get_portfolio_status(scope)
        proj = next(
            (p for p in status.get("projects", []) if p["project_id"] == project_id), None
        )
        if proj is None:
            return None
        sched, _ = self._plan(proj, scope)
        return sched.model_dump()

    def _plan(self, proj: dict, scope: str) -> tuple[ScheduleV1, AgentMessage]:
        start = proj.get("planned_start")
        cpm = compute_cpm(proj.get("tasks", []))
        crit = set(cpm.critical_path)
        sched = ScheduleV1(
            project_id=proj["project_id"],
            tasks=[
                ScheduledTask(
                    task_id=t.task_id,
                    wbs=t.wbs,
                    early_start=CpmResult.offset_date(start, t.early_start),
                    early_finish=CpmResult.offset_date(start, t.early_finish),
                    is_critical=t.task_id in crit,
                )
                for t in cpm.tasks
            ],
            critical_path=cpm.critical_path,
            projected_finish=cpm.projected_finish(start),
        )

        # delivery KPIs (§7): SPI, projected slippage
        spi = _spi(proj)
        if spi is not None:
            kpi.record(Axis.DELIVERY, "spi", spi, project_id=proj["project_id"])
        slip = _slippage_days(proj, cpm)
        if slip is not None:
            kpi.record(
                Axis.DELIVERY, "projected_slippage_days", slip, project_id=proj["project_id"]
            )

        msg = AgentMessage(
            sender=self.agent_id,
            receiver="A1",
            intent=Intent.INFORM,
            task_ref=f"{scope}/{proj['project_id']}",
            payload=MessagePayload(schema_="schedule.v1", data=sched.model_dump()),
            confidence=0.95,  # deterministic output -> high confidence
        )
        protocol.publish(msg)
        return sched, msg
