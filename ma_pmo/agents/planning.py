"""A2 Planning agent — schedule (CPM) (§3.2). [operational]

Flow: collect mock status -> CPM critical path (deterministic, no LLM) -> schedule.v1 ->
      delivery KPIs (SPI=EV/PV, projected slippage) -> inform message to A1.

A project without a start date cannot be dated, so A2 asks for it (core/questions.py) instead of
guessing. Without an answer in time it plans from the as-of date, the latest start it can
assume, and marks that schedule unconfirmed.
"""
from __future__ import annotations

from ma_pmo.agents import common, evm, lessons
from ma_pmo.agents.base import BaseAgent
from ma_pmo.agents.cpm import CpmResult, compute_cpm
from ma_pmo.connectors.base import IssueTrackerConnector
from ma_pmo.core import kpi, protocol, questions
from ma_pmo.core.i18n import tr
from ma_pmo.core.kpi import Axis
from ma_pmo.core.schemas.message import AgentMessage, Intent, MessagePayload
from ma_pmo.core.schemas.payloads.schedule_v1 import ScheduledTask, ScheduleV1
from ma_pmo.core.scope import DEFAULT_SCOPE
from ma_pmo.core.state.blackboard import PortfolioState
from ma_pmo.integrations.registry import get_tracker

_ROLE = """You are the PMO planning agent. Compute the CPM critical path."""


def _slippage_days(project: dict, cpm: CpmResult, forecast: str | None = None) -> int | None:
    """Projected slippage = deadline − forecast finish (negative means late). The earned-value
    forecast when there is one; the CPM finish (one person per task, 8 h/day) otherwise."""
    pf = forecast or cpm.projected_finish(project.get("planned_start"))
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


def _ask_start(project: dict) -> questions.Question:
    pid = project["project_id"]
    return questions.Question(
        key=f"{pid}.planned_start", project_id=pid, answer_type="date",
        ask=tr(f"When does {pid} start?", f"{pid}은(는) 언제 시작합니까?"),
        why=tr(f"{pid} has no start date, and the critical path is dated from it",
               f"{pid}에 시작일이 없는데, 임계 경로는 시작일부터 날짜를 매깁니다"),
        default=evm.as_of_date().isoformat())


class PlanningAgent(BaseAgent[ScheduleV1]):
    agent_id = "A2"
    function = "Planning (schedule/CPM)"
    role_prompt = _ROLE
    output_schema = ScheduleV1

    def __init__(self, tracker: IssueTrackerConnector | None = None) -> None:
        self.tracker = tracker or get_tracker()

    def run(self, state: PortfolioState) -> dict:
        scope = state.get("task_ref", DEFAULT_SCOPE)
        status = self.tracker.get_portfolio_status(scope)
        projects = status.get("projects", [])
        starts = questions.require(dict(state), self.agent_id, [
            _ask_start(p) for p in projects if not p.get("planned_start")])
        guessed = questions.unconfirmed(dict(state), list(starts))
        outputs, messages = [], []
        cited = lessons.evidence(lessons.on_board(state))  # empty unless the workflow lets it read
        for proj in projects:
            key = f"{proj['project_id']}.planned_start"
            if key in starts:
                proj = {**proj, "planned_start": starts[key]}
            sched, msg = self._plan(proj, scope, cited, confirmed=key not in guessed)
            out = common.entry(self.agent_id, "schedule.v1", sched)
            if key in guessed:  # planned from a default nobody confirmed
                out["unconfirmed"] = [key]
            outputs.append(out)
            messages.append(common.wire(msg))
        return {"outputs": outputs, "messages": messages}

    def plan_project(self, project_id: str, scope: str = DEFAULT_SCOPE) -> dict | None:
        proj = common.find_project(self.tracker, scope, project_id)
        if proj is None:
            return None
        sched, _ = self._plan(proj, scope)
        return sched.model_dump()

    def _plan(self, proj: dict, scope: str, cited: list | None = None,
              confirmed: bool = True) -> tuple[ScheduleV1, AgentMessage]:
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

        # delivery KPIs (§7): SPI and slippage from earned value at the as-of date
        spi = common.spi(proj)
        sched.forecast_finish = evm.forecast(proj, spi)
        if spi is not None:
            kpi.record(Axis.DELIVERY, "spi", spi, project_id=proj["project_id"])
        slip = _slippage_days(proj, cpm, sched.forecast_finish)
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
            # deterministic output -> high confidence; a guessed start date is for a person to see
            confidence=0.95 if confirmed else 0.5,
            evidence=cited or [],  # lessons A7 found, cited next to the estimate
        )
        protocol.publish(msg)
        return sched, msg
