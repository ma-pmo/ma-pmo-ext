"""A6 Governance agent — methodology/quality gates (§3.2). [operational]

Flow: collect mock status -> deterministic gate review (fact check, no LLM) -> gate_review.v1
      -> gate KPI (delivery axis) -> conditional/fail sets human_gate_required (approval).
"""
from __future__ import annotations

from ma_pmo.agents.base import BaseAgent
from ma_pmo.agents.gates import evaluate_gate, normalize_gate
from ma_pmo.connectors.jira_mock import MockJiraConnector
from ma_pmo.core import kpi, protocol
from ma_pmo.core.kpi import Axis
from ma_pmo.core.schemas.message import AgentMessage, Intent, MessagePayload
from ma_pmo.core.schemas.payloads.gate_review_v1 import ChecklistItem, GateReviewV1
from ma_pmo.core.state.blackboard import PortfolioState

_ROLE = """You are the PMO governance agent. Review deliverables against gate criteria
and checklists."""

# decision -> delivery-axis KPI value (pass=1, conditional=0.5, fail=0)
_SCORE = {"pass": 1.0, "conditional": 0.5, "fail": 0.0}


class GovernanceAgent(BaseAgent[GateReviewV1]):
    agent_id = "A6"
    function = "Governance (gates/quality)"
    role_prompt = _ROLE
    output_schema = GateReviewV1

    def __init__(self, tracker: MockJiraConnector | None = None) -> None:
        self.tracker = tracker or MockJiraConnector()

    def run(self, state: PortfolioState) -> dict:
        scope = state.get("task_ref", "PORTFOLIO#2026-Q1")
        gate = normalize_gate(state.get("gate", "G2-planning"))
        status = self.tracker.get_portfolio_status(scope)
        outputs, messages = [], []
        for proj in status.get("projects", []):
            review, msg = self._review(proj, gate, scope)
            outputs.append(
                {"agent": self.agent_id, "schema": "gate_review.v1", "data": review.model_dump()}
            )
            messages.append(msg.model_dump(by_alias=True, mode="json"))
        return {"outputs": outputs, "messages": messages}

    def review_project(
        self, project_id: str, gate: str = "G2-planning", scope: str = "PORTFOLIO#2026-Q1"
    ) -> dict | None:
        status = self.tracker.get_portfolio_status(scope)
        proj = next(
            (p for p in status.get("projects", []) if p["project_id"] == project_id), None
        )
        if proj is None:
            return None
        review, _ = self._review(proj, gate, scope)
        return review.model_dump()

    def _review(self, proj: dict, gate: str, scope: str) -> tuple[GateReviewV1, AgentMessage]:
        decision, criteria, conditions = evaluate_gate(proj, gate)
        review = GateReviewV1(
            project_id=proj["project_id"],
            gate=gate,
            decision=decision,
            checklist=[
                ChecklistItem(criterion=c.name, passed=c.passed, note=c.note) for c in criteria
            ],
            conditions=conditions,
        )

        kpi.record(
            Axis.DELIVERY,
            "gate_review",
            _SCORE[decision],
            project_id=proj["project_id"],
            meta={"gate": gate, "decision": decision},
        )

        gate_required = decision in {"conditional", "fail"}  # anything but pass needs human review
        msg = AgentMessage(
            sender=self.agent_id,
            receiver="A1",
            intent=Intent.PROPOSE if gate_required else Intent.INFORM,
            task_ref=f"{scope}/{proj['project_id']}",
            payload=MessagePayload(schema_="gate_review.v1", data=review.model_dump()),
            confidence=0.95,  # deterministic
            human_gate_required=gate_required,
        )
        protocol.publish(msg)
        return review, msg
