"""A2 planning output — schedule.v1."""
from __future__ import annotations

from pydantic import BaseModel, Field


class ScheduledTask(BaseModel):
    task_id: str
    wbs: str
    early_start: str
    early_finish: str
    is_critical: bool = False


class ScheduleV1(BaseModel):
    project_id: str
    tasks: list[ScheduledTask]
    critical_path: list[str] = Field(default_factory=list)
    projected_finish: str | None = None
