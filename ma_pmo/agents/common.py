"""Small pieces every built-in worker uses the same way."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from ma_pmo.connectors.base import IssueTrackerConnector
from ma_pmo.core.schemas.message import AgentMessage


def entry(agent_id: str, schema: str, data: BaseModel) -> dict[str, Any]:
    """One item of a worker's `outputs`."""
    return {"agent": agent_id, "schema": schema, "data": data.model_dump()}


def wire(message: AgentMessage) -> dict[str, Any]:
    """A message as a worker returns it under `messages`."""
    return message.model_dump(by_alias=True, mode="json")


def find_project(tracker: IssueTrackerConnector, scope: str, project_id: str) -> dict | None:
    """One project of the portfolio `scope`, as the tracker reports it, or None."""
    status = tracker.get_portfolio_status(scope)
    return next((p for p in status.get("projects", []) if p["project_id"] == project_id), None)


def spi(project: dict) -> float | None:
    """SPI = EV/PV (schedule performance index): PV is the total effort, EV the
    completion-weighted effort."""
    tasks = project.get("tasks", [])
    pv = sum(t.get("effort", 0.0) for t in tasks)
    if pv <= 0:
        return None
    ev = sum(t.get("effort", 0.0) * (t.get("percent_complete", 0.0) / 100.0) for t in tasks)
    return round(ev / pv, 3)
