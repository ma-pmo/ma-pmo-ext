"""POST /webhooks/issue — issue-tracker event intake (§2.2, event-driven).

The place to receive real Jira/Redmine webhooks and trigger the relevant agents.
Currently: issue_updated/sprint_closed events immediately trigger A4 (risk) early detection.
(Without an LLM, A4 falls back to its rule-based alert.)
"""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from ma_pmo.agents.risk import RiskAgent
from ma_pmo.core.scope import DEFAULT_SCOPE

router = APIRouter(tags=["webhooks"])

_RISK_TRIGGERS = {"issue_updated", "sprint_closed", "burndown_updated"}


class IssueEvent(BaseModel):
    project_id: str
    event_type: str  # e.g. issue_updated, sprint_closed
    scope: str = DEFAULT_SCOPE
    payload: dict = {}


@router.post("/webhooks/issue")
def issue_webhook(event: IssueEvent) -> dict:
    import json

    from fastapi import HTTPException

    from ma_pmo.core import commitments, safety

    try:  # tracker text that carries instructions to the model (roadmap 10)
        safety.guard_input(json.dumps(event.payload, ensure_ascii=False), "webhook")
    except safety.InputBlocked as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    commitments.check_tracker()  # what the tracker now shows done, then what is overdue
    commitments.sweep_quietly()
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
