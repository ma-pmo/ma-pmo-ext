"""A4 Risk agent — early risk detection (§3.2). [operational]

Flow: collect mock status -> deterministic signal analysis (rule-based baseline) ->
      LLM severity/mitigation per flagged project (validated as risk_alert.v1) ->
      store Risk (detected_at) -> record RLT (lead time) KPI ->
      message to A1 (high/critical sets human_gate_required -> approval gate). Its confidence
      is the calibrated chance that the tasks it names slip (`risk_calibration.py`).
"""
from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

from ma_pmo.agents import common, risk_calibration
from ma_pmo.agents.base import BaseAgent
from ma_pmo.agents.risk_signals import (
    SIGNAL_FIELDS,
    ProjectSignals,
    baseline_severity,
    compute_signals,
)
from ma_pmo.connectors.base import IssueTrackerConnector
from ma_pmo.core import kpi, llm, protocol, tracing
from ma_pmo.core.i18n import tr
from ma_pmo.core.kpi import Axis
from ma_pmo.core.obs import get_logger
from ma_pmo.core.schemas.message import AgentMessage, EvidenceRef, Intent, MessagePayload
from ma_pmo.core.schemas.payloads.risk_alert_v1 import RiskAlertV1
from ma_pmo.core.scope import DEFAULT_SCOPE
from ma_pmo.core.state.blackboard import PortfolioState
from ma_pmo.db.models import Risk
from ma_pmo.db.session import get_session
from ma_pmo.integrations.registry import get_tracker

_ROLE = """You are the PMO risk agent. Given deterministically extracted risk signals
(schedule slack, stalled burndown, blocked dependencies, etc.), rate the severity
(low/medium/high/critical) and give concrete mitigations with rationale. Base your judgment
on the signals without exaggeration. lead_time_days is the lead time in days from this alert
until the risk would actually materialize."""

_HIGH = {"high", "critical"}
_log = get_logger("risk")


def _missed(project_id: str) -> list[str]:
    from ma_pmo.core import commitments

    try:
        return commitments.violated_for(project_id)
    except Exception:  # a database without the ledger: no signal from it
        return []


def _with_missed(status: dict) -> list[ProjectSignals]:
    """The projects with a signal, counting commitments they missed (roadmap 9)."""
    found = []
    for p in status.get("projects", []):
        sig = compute_signals(p)
        sig.missed_commitments = _missed(p["project_id"])
        if sig.has_signal:
            found.append(sig)
    return found


class RiskAgent(BaseAgent[RiskAlertV1]):
    agent_id = "A4"
    function = "Risk (early detection)"
    role_prompt = _ROLE
    output_schema = RiskAlertV1

    def __init__(self, tracker: IssueTrackerConnector | None = None) -> None:
        self.tracker = tracker or get_tracker()

    # ── LangGraph node: scan the whole portfolio ─────────────────
    def run(self, state: PortfolioState) -> dict:
        scope = state.get("task_ref", DEFAULT_SCOPE)
        status = self.tracker.get_portfolio_status(scope)
        signals = _with_missed(status)
        projects = {p["project_id"]: p for p in status.get("projects", [])}

        outputs, messages = [], []
        for sig in signals:
            alert, msg = self._assess(sig, scope, projects.get(sig.project_id, {}))
            outputs.append(common.entry(self.agent_id, "risk_alert.v1", alert))
            messages.append(common.wire(msg))
        return {"outputs": outputs, "messages": messages}

    # ── single-project assessment (also reused by webhooks) ──────
    def assess_project(self, project_id: str, scope: str = DEFAULT_SCOPE) -> dict | None:
        proj = common.find_project(self.tracker, scope, project_id)
        if proj is None:
            return None
        sig = compute_signals(proj)
        sig.missed_commitments = _missed(project_id)
        if not sig.has_signal:
            return {
                "project_id": project_id,
                "risk": None,
                "note": tr("no significant signal", "유의 신호 없음"),
            }
        alert, _ = self._assess(sig, scope, proj)
        return {"project_id": project_id, "risk": alert.model_dump()}

    @staticmethod
    def _unsure(severity: str, baseline: str) -> bool:
        """A fast model's rating is not trusted when it is two or more levels from the rule
        baseline (e.g. low against high): the cheap model is the one likely to be wrong, and the
        standard model is asked instead (roadmap 11, step 3; `MA_PMO_A4_DEFER=false` turns it
        off). Only on a `model_tier: fast` step."""
        from ma_pmo.core.config import get_settings

        if not get_settings().a4_defer or not llm.on_fast_model():
            return False
        order = ["low", "medium", "high", "critical"]
        return abs(order.index(severity) - order.index(baseline)) >= 2

    # ── internal: signal -> LLM rating -> store -> KPI -> message ─
    def _assess(self, sig: ProjectSignals, scope: str,
                project: dict | None = None) -> tuple[RiskAlertV1, AgentMessage]:
        baseline = baseline_severity(sig)
        prompt = (
            f"Scope: {scope}\nProject: {sig.project_id}\n"
            "Rule-based signals (JSON):\n"
            f"{json.dumps(sig.as_dict(), ensure_ascii=False, indent=2)}\n"
            f"Rule-based baseline severity: {baseline}\n\n"
            "Rate the risk from these signals. Keep project_id unchanged."
        )
        path = "llm"
        deferred = False
        try:
            alert = self.structured(prompt)
            if self._unsure(alert.severity, baseline):  # ask the standard model instead
                try:
                    alert = llm.complete_structured(self.role_prompt, prompt, RiskAlertV1,
                                                    agent=self.agent_id,
                                                    model=llm.model_for("standard"))
                    deferred = True
                    tracing.mark_fallback("A4 fast model deferred to standard")
                except Exception as e:  # keep the fast answer if the standard one fails
                    _log.warning("risk_defer_failed", project_id=sig.project_id,
                                 error=type(e).__name__)
        except Exception as e:  # no LLM / outage / invalid output -> rule-based risk alert
            _log.warning("risk_fallback", project_id=sig.project_id, error=type(e).__name__)
            tracing.mark_fallback("A4 risk", e)
            path = "rule"
            alert = RiskAlertV1(
                project_id=sig.project_id,
                signal=(
                    tr(
                        f"status {sig.status}, slack {sig.schedule_slack_days}d, "
                        f"stalled {sig.stalled_tasks}, blocked {sig.blocked_tasks}",
                        f"상태 {sig.status}, 여유 {sig.schedule_slack_days}일, "
                        f"정체 {sig.stalled_tasks}, 차단 {sig.blocked_tasks}",
                    )
                    + (tr(f", missed {sig.missed_commitments}",
                          f", 미이행 {sig.missed_commitments}") if sig.missed_commitments else "")
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
                meta={  # which path rated it: on the rule path there is no LLM rating to compare
                    "risk_id": risk_id,
                    "path": path,
                    "severity_llm": alert.severity if path == "llm" else None,
                    "severity_baseline": baseline,
                    "agreement": alert.severity == baseline if path == "llm" else None,
                    "deferred": deferred,
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
            # the calibrated chance that the tasks this alert points at slip (risk_calibration.py)
            confidence=risk_calibration.alert_confidence(sig, project or {}),
            human_gate_required=gate,  # high severity goes through the human approval gate
            evidence=[EvidenceRef(kind="tracker", ref=sig.project_id, field=f)
                      for f in SIGNAL_FIELDS if f in (project or {})],  # what the signals read
        )
        protocol.publish(msg)
        return alert, msg
