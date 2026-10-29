"""A4 Risk agent — early risk detection (§3.2). [operational]

Flow: collect mock status -> deterministic signal analysis (rule-based baseline) ->
      LLM severity/mitigation per flagged project (validated as risk_alert.v1) ->
      store Risk (detected_at) -> record RLT (lead time) KPI ->
      message to A1 (high/critical sets human_gate_required -> approval gate).
"""
from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

from ma_pmo.agents.base import BaseAgent
from ma_pmo.agents.risk_signals import ProjectSignals, analyze_portfolio, baseline_severity
from ma_pmo.connectors.jira_mock import MockJiraConnector
from ma_pmo.core import kpi, protocol
from ma_pmo.core.i18n import tr
from ma_pmo.core.kpi import Axis
from ma_pmo.core.schemas.message import AgentMessage, Intent, MessagePayload
from ma_pmo.core.schemas.payloads.risk_alert_v1 import RiskAlertV1
from ma_pmo.core.state.blackboard import PortfolioState
from ma_pmo.db.models import Risk
from ma_pmo.db.session import get_session

_ROLE = """You are the PMO risk agent. Given deterministically extracted risk signals
(schedule slack, stalled burndown, blocked dependencies, etc.), rate the severity
(low/medium/high/critical) and give concrete mitigations with rationale. Base your judgment
on the signals without exaggeration. lead_time_days is the lead time in days from this alert
until the risk would actually materialize."""

_HIGH = {"high", "critical"}


class RiskAgent(BaseAgent[RiskAlertV1]):
    agent_id = "A4"
    function = "Risk (early detection)"
    role_prompt = _ROLE
    output_schema = RiskAlertV1

    def __init__(self, tracker: MockJiraConnector | None = None) -> None:
        self.tracker = tracker or MockJiraConnector()

    # ── LangGraph node: scan the whole portfolio ─────────────────
    def run(self, state: PortfolioState) -> dict:
        scope = state.get("task_ref", "PORTFOLIO#2026-Q1")
        status = self.tracker.get_portfolio_status(scope)
        signals = analyze_portfolio(status)

        outputs, messages = [], []
        for sig in signals:
            alert, msg = self._assess(sig, scope)
            outputs.append(
                {"agent": self.agent_id, "schema": "risk_alert.v1", "data": alert.model_dump()}
            )
            messages.append(msg.model_dump(by_alias=True, mode="json"))
        return {"outputs": outputs, "messages": messages}

    # ── single-project assessment (also reused by webhooks) ──────
    def assess_project(self, project_id: str, scope: str = "PORTFOLIO#2026-Q1") -> dict | None:
        status = self.tracker.get_portfolio_status(scope)
        proj = next(
            (p for p in status.get("projects", []) if p["project_id"] == project_id), None
        )
        if proj is None:
            return None
        from ma_pmo.agents.risk_signals import compute_signals

        sig = compute_signals(proj)
        if not sig.has_signal:
            return {
                "project_id": project_id,
                "risk": None,
                "note": tr("no significant signal", "유의 신호 없음"),
            }
        alert, _ = self._assess(sig, scope)
        return {"project_id": project_id, "risk": alert.model_dump()}

    # ── internal: signal -> LLM rating -> store -> KPI -> message ─
    def _assess(self, sig: ProjectSignals, scope: str) -> tuple[RiskAlertV1, AgentMessage]:
        baseline = baseline_severity(sig)
        prompt = (
            f"Scope: {scope}\nProject: {sig.project_id}\n"
            "Rule-based signals (JSON):\n"
            f"{json.dumps(sig.as_dict(), ensure_ascii=False, indent=2)}\n"
            f"Rule-based baseline severity: {baseline}\n\n"
            "Rate the risk from these signals. Keep project_id unchanged."
        )
        try:
            alert = self.structured(prompt)
        except Exception:  # no LLM / outage -> rule-based risk alert fallback
            alert = RiskAlertV1(
                project_id=sig.project_id,
                signal=(
                    tr(
                        f"status {sig.status}, slack {sig.schedule_slack_days}d, "
                        f"stalled {sig.stalled_tasks}, blocked {sig.blocked_tasks}",
                        f"상태 {sig.status}, 여유 {sig.schedule_slack_days}일, "
                        f"정체 {sig.stalled_tasks}, 차단 {sig.blocked_tasks}",
                    )
                ),
                severity=baseline,
                lead_time_days=float(sig.schedule_slack_days)
                if sig.schedule_slack_days is not None
                else None,
                mitigation=tr(
                    "Rule-based alert: review the critical path and resource reallocation",
                    "규칙기반 경보: 임계경로 재검토 및 자원 재배분 검토",
                ),
                rationale=tr(
                    "Deterministic signal analysis (rule-based baseline)",
                    "결정론적 신호 분석(규칙기반 baseline)",
                ),
            )
        alert.project_id = sig.project_id  # guard against LLM rewriting the ID

        detected_at = datetime.now(UTC)
        risk_id = f"RISK-{uuid.uuid4().hex[:8]}"
        with get_session() as s:
            s.add(
                Risk(
                    id=risk_id,
                    project_id=sig.project_id,
                    signal=alert.signal,
                    severity=alert.severity,
                    detected_at=detected_at,
                    mitigation=alert.mitigation,
                )
            )

        # RLT (lead time) KPI — paper H3. Also records whether rule-based and LLM severity agree.
        if alert.lead_time_days is not None:
            kpi.record(
                Axis.RISK,
                "risk_lead_time_days",
                alert.lead_time_days,
                project_id=sig.project_id,
                meta={
                    "risk_id": risk_id,
                    "severity_llm": alert.severity,
                    "severity_baseline": baseline,
                    "agreement": alert.severity == baseline,
                },
            )
        kpi.record(Axis.RISK, "risk_detected", 1, project_id=sig.project_id)

        gate = alert.severity in _HIGH
        msg = AgentMessage(
            sender=self.agent_id,
            receiver="A1",
            intent=Intent.PROPOSE if gate else Intent.INFORM,
            task_ref=f"{scope}/{sig.project_id}",
            payload=MessagePayload(schema_="risk_alert.v1", data=alert.model_dump()),
            confidence=0.85,
            human_gate_required=gate,  # high severity goes through the human approval gate
        )
        protocol.publish(msg)
        return alert, msg
