"""A4 risk output — risk_alert.v1."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# A fixed set, in the type: every reader compares it with sets such as {"high", "critical"}, so
# "High" or "높음" would silently skip the approval gate, notifications and review.
Severity = Literal["low", "medium", "high", "critical"]


class RiskAlertV1(BaseModel):
    project_id: str
    signal: str  # detected signal (e.g. stalled burndown, dependency delay)
    severity: Severity
    lead_time_days: float | None = Field(
        default=None, description="lead time (RLT): from early warning to expected materialization"
    )
    mitigation: str
    rationale: str
