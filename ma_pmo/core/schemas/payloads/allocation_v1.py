"""A3 resource output — allocation.v1."""
from __future__ import annotations

from pydantic import BaseModel, Field


class AllocationLine(BaseModel):
    project_id: str
    resource_id: str
    week: str  # ISO week, e.g. 2026-W03
    hours: float = Field(ge=0.0)


class AllocationV1(BaseModel):
    plan: list[AllocationLine]
    overload_alerts: list[str] = Field(default_factory=list)
    utilization_pct: float | None = None
