"""A5 Reporting agent — stakeholder communication (§3.2). [operational]

Flow: collect mock issue-tracker status -> generate executive report with the LLM
      (validated as report.v1) -> store report -> record RCT (report cycle time) KPI
      -> publish inform message to A1.

When the workflow lets this step read earlier posts (`reads`), A5 checks its report before
publishing it: a project A4 rated medium or above but missing from the key risks is added
(self-check), and A5 posts a review.v1 verdict on the report citing A4's alerts.
"""
from __future__ import annotations

import json
import time
import uuid

from ma_pmo.agents import common, cross_checks
from ma_pmo.agents.base import BaseAgent
from ma_pmo.connectors.base import IssueTrackerConnector
from ma_pmo.core import kpi, protocol, tracing
from ma_pmo.core.i18n import tr
from ma_pmo.core.schemas.message import AgentMessage, Intent, MessagePayload
from ma_pmo.core.schemas.payloads.report_v1 import ProjectStatusLine, ReportV1
from ma_pmo.core.scope import DEFAULT_SCOPE
from ma_pmo.core.state.blackboard import PortfolioState
from ma_pmo.db.models import Report
from ma_pmo.db.session import get_session
from ma_pmo.integrations.registry import get_tracker


def _fallback_report(status: dict, scope: str) -> ReportV1:
    """Deterministic executive report from status data, without an LLM."""
    projects = status.get("projects", [])
    reds = [p for p in projects if p.get("status") == "red"]
    ambers = [p for p in projects if p.get("status") == "amber"]
    avg = round(
        sum(p.get("percent_complete", 0.0) for p in projects) / len(projects), 1
    ) if projects else 0.0
    return ReportV1(
        scope=scope,
        executive_summary=(
            tr(
                f"{len(projects)} projects: {len(reds)} red, {len(ambers)} amber, "
                f"average progress {avg}%. (rule-based automatic report)",
                f"{len(projects)}개 프로젝트 중 red {len(reds)}건, amber {len(ambers)}건, "
                f"평균 진척 {avg}%. (규칙기반 자동 보고)",
            )
        ),
        project_status=[
            ProjectStatusLine(
                project_id=p["project_id"],
                name=p["project_id"],
                status=p.get("status", "green"),
                percent_complete=p.get("percent_complete", 0.0),
                headline=(
                    tr(
                        f"progress {p.get('percent_complete', 0.0)}% · due {p.get('deadline')}",
                        f"진척 {p.get('percent_complete', 0.0)}% · 마감 {p.get('deadline')}",
                    )
                ),
            )
            for p in projects
        ],
        key_risks=[
            tr(
                f"{p['project_id']} status {p.get('status')}",
                f"{p['project_id']} 상태 {p.get('status')}",
            )
            for p in reds + ambers
        ],
        recommended_actions=(
            [tr("Review resource reallocation for red projects", "red 프로젝트 자원 재배분 검토")]
            if reds
            else [tr("Hold course and keep monitoring", "현 상태 유지 및 모니터링")]
        ),
    )

_ROLE = """You are the PMO reporting agent. Given portfolio status data, write a status
report for executives. Stay factual, surface delays and risks clearly, and give actionable
recommendations. Rate status as green/amber/red."""


def _with_upstream_risks(report: ReportV1, board: list[dict], steps: list[dict]) -> ReportV1:
    """The report with every A4 alert of medium or above among its key risks."""
    alerts = cross_checks.risks_to_report(board, steps) or []
    check = cross_checks.covers_risks(report.key_risks, board, steps)
    if check is None or check.verdict == "VERIFIED":
        return report
    cited = {e.ref for e in check.evidence}
    added = [tr(f"{a['data']['project_id']} risk {a['data']['severity']} (A4): "
                f"{a['data'].get('signal', '')}",
                f"{a['data']['project_id']} 리스크 {a['data']['severity']}(A4): "
                f"{a['data'].get('signal', '')}").strip()
             for a in alerts if a["message_id"] in cited]
    return report.model_copy(update={"key_risks": [*report.key_risks, *added]})


class ReportingAgent(BaseAgent[ReportV1]):
    agent_id = "A5"
    function = "Reporting (stakeholder communication)"
    role_prompt = _ROLE
    output_schema = ReportV1

    def __init__(self, tracker: IssueTrackerConnector | None = None) -> None:
        self.tracker = tracker or get_tracker()

    def run(self, state: PortfolioState) -> dict:
        t0 = time.monotonic()
        scope = state.get("task_ref", DEFAULT_SCOPE)
        goal = state.get("goal", "Generate portfolio executive report")

        status = self.tracker.get_portfolio_status(scope)
        user_prompt = (
            f"Goal: {goal}\nScope: {scope}\n\n"
            "Current portfolio status (JSON):\n"
            f"{json.dumps(status, ensure_ascii=False, indent=2)}\n\n"
            "Write the executive report from this data."
        )
        try:
            report = self.structured(user_prompt)
        except Exception as e:  # no LLM / outage -> deterministic report fallback
            tracing.mark_fallback("A5 report", e)
            report = _fallback_report(status, scope)
        if "board" in state:  # self-check: every risk A4 raised belongs in the key risks
            report = _with_upstream_risks(report, state["board"], state.get("board_steps", []))

        # persist output
        report_id = f"RPT-{uuid.uuid4().hex[:8]}"
        with get_session() as s:
            s.add(
                Report(
                    id=report_id,
                    scope=scope,
                    generated_by=self.agent_id,
                    content=report.model_dump(),
                )
            )

        # RCT (report cycle time) — paper H1
        elapsed = time.monotonic() - t0
        kpi.record_report_cycle_time(elapsed, scope=scope)

        # publish structured message to A1 (append-only log)
        msg = AgentMessage(
            sender=self.agent_id,
            receiver="A1",
            intent=Intent.INFORM,
            task_ref=scope,
            payload=MessagePayload(schema_="report.v1", data=report.model_dump()),
            confidence=0.9,
        )
        msg = protocol.publish(msg)
        outputs = [common.entry(self.agent_id, "report.v1", report)]
        if "board" in state:
            verdict = cross_checks.covers_risks(report.key_risks, state["board"],
                                                state.get("board_steps", []))
            if verdict is not None:
                outputs.append(cross_checks.publish_review(
                    self.agent_id, verdict, msg.message_id, msg.task_ref))
        return {"outputs": outputs, "messages": [common.wire(msg)]}
