"""POST /webhooks/issue — issue-tracker event intake (§2.2, event-driven).

The place to receive real Jira/Redmine webhooks and trigger the relevant agents.
Currently: issue_updated/sprint_closed events immediately trigger A4 (risk) early detection.
(Without an LLM, A4 falls back to its rule-based alert.)
"""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from ma_pmo.agents.risk import RiskAgent

router = APIRouter(tags=["webhooks"])

_RISK_TRIGGERS = {"issue_updated", "sprint_closed", "burndown_updated"}


class IssueEvent(BaseModel):
    project_id: str
    event_type: str  # e.g. issue_updated, sprint_closed
    scope: str = "PORTFOLIO#2026-Q1"
    payload: dict = {}


@router.post("/webhooks/issue")
def issue_webhook(event: IssueEvent) -> dict:
    triggered = None
    if event.event_type in _RISK_TRIGGERS:
        # event-driven: reassess risk for this project only (A4)
        triggered = RiskAgent().assess_project(event.project_id, scope=event.scope)
    return {
        "received": True,
        "project_id": event.project_id,
        "event_type": event.event_type,
        "triggered_agent": "A4" if triggered is not None else None,
        "result": triggered,
    }
