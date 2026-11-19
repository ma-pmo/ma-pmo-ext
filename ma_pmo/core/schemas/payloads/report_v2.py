"""A5's full report — report.v2: report.v1's narrative on top of computed facts.

The facts (`ReportFacts`) are computed from the tracker and the previous report, never by an LLM:
KPIs with their previous values, each project's status, progress, forecast and change since the
last report, and tolerance checks. Every fact has an `id` so that text can cite it. The structure
follows a PRINCE2 highlight report: period, RAG summary, tolerance status, issues and risks.

Reports come in kinds a PMO uses for different readers (`reports/kinds.py`): a status
(highlight) report, a one-page executive summary, an exception report, a gate decision pack and
a closure report. The kind decides which sections are shown and what the narrative is about; the
facts are the same. Risks, gate decisions and lessons come from what earlier steps posted, when
the workflow lets A5 read them.

A5 still publishes `report.v1` (`ReportV2.to_v1()`) to the other agents; report.v2 is what is
stored and what people read.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from ma_pmo.core.schemas.payloads.report_v1 import ProjectStatusLine, ReportV1

Status = Literal["green", "amber", "red"]
Kind = Literal["status", "executive", "exception", "gate", "closure"]


class KpiFact(BaseModel):
    id: str  # "kpi.spi"
    label: str
    value: float | None
    previous: float | None = None  # in the previous report of the same scope
    unit: str = ""
    better: Literal["higher", "lower"] = "higher"

    @property
    def delta(self) -> float | None:
        if self.value is None or self.previous is None:
            return None
        return round(self.value - self.previous, 3)


class ProjectFact(BaseModel):
    id: str  # "project.PROJ-14"
    project_id: str
    status: Status
    previous_status: Status | None = None
    percent_complete: float = Field(ge=0.0, le=100.0)
    previous_percent_complete: float | None = None
    spi: float | None = None
    deadline: str | None = None
    forecast_finish: str | None = None  # CPM from the planned start
    slack_days: int | None = None  # deadline − forecast finish; negative is late


class ToleranceCheck(BaseModel):
    id: str  # "tolerance.PROJ-14.schedule"
    project_id: str
    dimension: Literal["schedule", "spi"]
    value: float
    limit: float
    breached: bool


class RiskFact(BaseModel):
    id: str  # "risk.<message id>"
    project_id: str
    severity: str
    signal: str
    mitigation: str = ""
    message_id: str


class GateFact(BaseModel):
    id: str  # "gate.PROJ-14.G3-execution"
    project_id: str
    gate: str
    decision: str  # pass | conditional | fail
    failed: list[str] = Field(default_factory=list)  # checklist criteria not passed
    conditions: list[str] = Field(default_factory=list)
    message_id: str


class LessonFact(BaseModel):
    id: str  # "lesson.LL-012"
    source_id: str
    excerpt: str
    message_id: str


class ApprovalFact(BaseModel):
    id: str  # "approval.12"
    approval_id: int
    task_ref: str
    project_id: str | None = None
    sender: str
    schema_: str = Field(default="", alias="schema")
    requested_at: str
    held_by_review: bool = False  # the commit gate held it, not low confidence

    model_config = {"populate_by_name": True}


class ReportFacts(BaseModel):
    as_of: str  # YYYY-MM-DD
    projects_in_scope: list[str] | None = None  # None: the whole portfolio
    period_start: str | None = None  # the previous report's as-of date
    previous_report_id: str | None = None
    kpis: list[KpiFact] = Field(default_factory=list)
    projects: list[ProjectFact] = Field(default_factory=list)
    tolerances: list[ToleranceCheck] = Field(default_factory=list)
    risks: list[RiskFact] = Field(default_factory=list)  # from A4, when readable
    gates: list[GateFact] = Field(default_factory=list)  # from A6, when readable
    lessons: list[LessonFact] = Field(default_factory=list)  # from A7, when readable
    approvals: list[ApprovalFact] = Field(default_factory=list)  # waiting in the queue
    board_read: bool = False  # whether the step could read earlier posts at all

    @property
    def breaches(self) -> list[ToleranceCheck]:
        return [t for t in self.tolerances if t.breached]


class ReportV2(BaseModel):
    """Structured report (A5): header, computed facts, narrative."""

    scope: str
    kind: Kind = "status"
    title: str = ""
    audience: Literal["executive", "team"] = "team"
    path: Literal["llm", "rule"]  # who wrote the narrative
    language: str = "en"
    overall_status: Status
    facts: ReportFacts
    executive_summary: str
    project_status: list[ProjectStatusLine]
    key_risks: list[str] = Field(default_factory=list)
    recommended_actions: list[str] = Field(default_factory=list)

    def to_v1(self) -> ReportV1:
        return ReportV1(
            scope=self.scope,
            executive_summary=self.executive_summary,
            project_status=self.project_status,
            key_risks=self.key_risks,
            recommended_actions=self.recommended_actions,
        )
