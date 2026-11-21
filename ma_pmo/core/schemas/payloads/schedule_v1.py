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
    # CPM from the planned start, each task at 8 h/day by one person: the order of the work
    projected_finish: str | None = None
    # earned value at the as-of date (agents/evm.py): when the work, at its pace, will end
    forecast_finish: str | None = None
