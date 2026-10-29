"""A5 reporting output — report.v1."""
from __future__ import annotations

from pydantic import BaseModel, Field


class ProjectStatusLine(BaseModel):
    project_id: str
    name: str
    status: str  # green | amber | red
    percent_complete: float = Field(ge=0.0, le=100.0)
    headline: str


class ReportV1(BaseModel):
    """Structured executive report (A5)."""

    scope: str  # e.g. PORTFOLIO#2026-Q1
    executive_summary: str
    project_status: list[ProjectStatusLine]
    key_risks: list[str] = Field(default_factory=list)
    recommended_actions: list[str] = Field(default_factory=list)
