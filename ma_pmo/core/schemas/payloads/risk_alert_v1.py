"""A4 risk output — risk_alert.v1."""
from __future__ import annotations

from pydantic import BaseModel, Field


class RiskAlertV1(BaseModel):
    project_id: str
    signal: str  # detected signal (e.g. stalled burndown, dependency delay)
    severity: str  # low | medium | high | critical
    lead_time_days: float | None = Field(
        default=None, description="lead time (RLT): from early warning to expected materialization"
    )
    mitigation: str
    rationale: str
