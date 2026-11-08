"""A3 resource output — allocation.v1."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class AllocationLine(BaseModel):
    project_id: str
    resource_id: str
    week: str  # ISO week, e.g. 2026-W03
    hours: float = Field(ge=0.0)


class Unstaffed(BaseModel):
    """Work of a project that no one can take within the horizon (the reason, in data)."""

    project_id: str
    skill: str
    remaining_hours: float = Field(ge=0.0)
    reason: Literal["no_skill", "capacity"]


class AllocationV1(BaseModel):
    plan: list[AllocationLine]
    overload_alerts: list[str] = Field(default_factory=list)
    utilization_pct: float | None = None
    unstaffed: list[Unstaffed] = Field(default_factory=list)  # the alerts above, as data
