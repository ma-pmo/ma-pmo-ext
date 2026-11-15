"""A6 governance output — gate_review.v1."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Decision = Literal["pass", "conditional", "fail"]


class ChecklistItem(BaseModel):
    criterion: str
    passed: bool
    note: str = ""


class GateReviewV1(BaseModel):
    project_id: str
    gate: str  # e.g. G2-planning
    decision: Decision
    checklist: list[ChecklistItem] = Field(default_factory=list)
    conditions: list[str] = Field(default_factory=list)
