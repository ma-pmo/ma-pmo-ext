"""A6 governance output — gate_review.v1."""
from __future__ import annotations

from pydantic import BaseModel, Field


class ChecklistItem(BaseModel):
    criterion: str
    passed: bool
    note: str = ""


class GateReviewV1(BaseModel):
    project_id: str
    gate: str  # e.g. G2-planning
    decision: str  # pass | conditional | fail
    checklist: list[ChecklistItem] = Field(default_factory=list)
    conditions: list[str] = Field(default_factory=list)
