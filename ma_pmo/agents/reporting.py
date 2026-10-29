"""A5 Reporting agent — stakeholder communication (§3.2). [operational]

Flow: collect mock issue-tracker status -> generate executive report with the LLM
      (validated as report.v1) -> store report -> record RCT (report cycle time) KPI
      -> publish inform message to A1.
"""
from __future__ import annotations

import json
import time
import uuid

from ma_pmo.agents.base import BaseAgent
from ma_pmo.connectors.jira_mock import MockJiraConnector
from ma_pmo.core import kpi, protocol
from ma_pmo.core.i18n import tr
from ma_pmo.core.schemas.message import AgentMessage, Intent, MessagePayload
from ma_pmo.core.schemas.payloads.report_v1 import ProjectStatusLine, ReportV1
from ma_pmo.core.state.blackboard import PortfolioState
from ma_pmo.db.models import Report
from ma_pmo.db.session import get_session


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


class ReportingAgent(BaseAgent[ReportV1]):
    agent_id = "A5"
    function = "Reporting (stakeholder communication)"
    role_prompt = _ROLE
    output_schema = ReportV1

    def __init__(self, tracker: MockJiraConnector | None = None) -> None:
        self.tracker = tracker or MockJiraConnector()

    def run(self, state: PortfolioState) -> dict:
        t0 = time.monotonic()
        scope = state.get("task_ref", "PORTFOLIO#2026-Q1")
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
        except Exception:  # no LLM / outage -> deterministic report fallback
            report = _fallback_report(status, scope)

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
        protocol.publish(msg)

        return {
            "outputs": [
                {"agent": self.agent_id, "schema": "report.v1", "data": report.model_dump()}
            ],
            "messages": [msg.model_dump(by_alias=True, mode="json")],
        }
