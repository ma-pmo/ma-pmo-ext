"""SQLAlchemy data models — paper §6.

Lightweight first (SQLite); the same models work unchanged on Postgres in production.

Every row belongs to a workspace (`Scoped`). Names people choose (portfolio, project, task,
resource and knowledge ids) are unique within a workspace, so those tables have a composite key
and composite foreign keys: a row cannot point at another workspace's project. Generated ids
(runs, messages, risks, reports) stay globally unique.
"""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    PrimaryKeyConstraint,
    String,
    Text,
    UniqueConstraint,
    event,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from ma_pmo.core import workspace
from ma_pmo.core.workspace import DEFAULT_WORKSPACE

__all__ = ["DEFAULT_WORKSPACE"]  # re-exported for callers that only know the models


def _utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class Workspace(Base):
    __tablename__ = "workspace"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class Membership(Base):
    """A role a principal (a key name, or a custom authenticator's subject) has in a workspace.

    Not `Scoped`: a request reads the caller's memberships before it knows its workspace."""

    __tablename__ = "membership"
    __table_args__ = (UniqueConstraint("workspace_id", "principal", "role", name="uq_membership"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspace.id"))
    principal: Mapped[str] = mapped_column(String, index=True)
    role: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class Scoped:
    """A row that belongs to one workspace."""

    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspace.id"), index=True)


@event.listens_for(Scoped, "init", propagate=True)
def _in_current_workspace(target: Scoped, args: tuple, kwargs: dict) -> None:
    # set on construction, so `merge` looks up the right composite key
    kwargs.setdefault("workspace_id", workspace.current())


def _key() -> PrimaryKeyConstraint:
    return PrimaryKeyConstraint("workspace_id", "id")


def _ref(column: str, table: str) -> ForeignKeyConstraint:
    return ForeignKeyConstraint(["workspace_id", column], [f"{table}.workspace_id", f"{table}.id"])


class Portfolio(Scoped, Base):
    __tablename__ = "portfolio"
    __table_args__ = (_key(),)
    id: Mapped[str] = mapped_column(String)
    name: Mapped[str] = mapped_column(String)
    period: Mapped[str] = mapped_column(String)  # e.g. 2026-Q1
    plan_start: Mapped[str | None] = mapped_column(String, nullable=True)  # ISO week, e.g. 2026-W03

    projects: Mapped[list[Project]] = relationship(back_populates="portfolio")


class Project(Scoped, Base):
    __tablename__ = "project"
    __table_args__ = (_key(), _ref("portfolio_id", "portfolio"))
    id: Mapped[str] = mapped_column(String)
    portfolio_id: Mapped[str] = mapped_column(String)
    skill: Mapped[str] = mapped_column(String, default="")
    planned_start: Mapped[str | None] = mapped_column(String, nullable=True)
    planned_finish: Mapped[str | None] = mapped_column(String, nullable=True)
    deadline: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, default="green")  # green|amber|red

    portfolio: Mapped[Portfolio] = relationship(back_populates="projects")
    tasks: Mapped[list[Task]] = relationship(back_populates="project")


class Task(Scoped, Base):
    __tablename__ = "task"
    __table_args__ = (_key(), _ref("project_id", "project"))
    id: Mapped[str] = mapped_column(String)
    project_id: Mapped[str] = mapped_column(String)
    wbs: Mapped[str] = mapped_column(String, default="")
    effort: Mapped[float] = mapped_column(Float, default=0.0)
    deps: Mapped[list] = mapped_column(JSON, default=list)  # task_id[]
    percent_complete: Mapped[float] = mapped_column(Float, default=0.0)

    project: Mapped[Project] = relationship(back_populates="tasks")


class Resource(Scoped, Base):
    __tablename__ = "resource"
    __table_args__ = (_key(),)
    id: Mapped[str] = mapped_column(String)
    skill: Mapped[str] = mapped_column(String, default="")
    capacity: Mapped[float] = mapped_column(Float, default=40.0)  # hours per week


class Allocation(Scoped, Base):
    __tablename__ = "allocation"
    __table_args__ = (_ref("project_id", "project"), _ref("resource_id", "resource"))
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(String)
    resource_id: Mapped[str] = mapped_column(String)
    week: Mapped[str] = mapped_column(String)
    hours: Mapped[float] = mapped_column(Float, default=0.0)


class Risk(Scoped, Base):
    __tablename__ = "risk"
    __table_args__ = (_ref("project_id", "project"),)
    id: Mapped[str] = mapped_column(String, primary_key=True)
    project_id: Mapped[str] = mapped_column(String)
    signal: Mapped[str] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(String, default="medium")
    detected_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    materialized_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    mitigation: Mapped[str] = mapped_column(Text, default="")


class Report(Scoped, Base):
    __tablename__ = "report"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    scope: Mapped[str] = mapped_column(String)
    generated_by: Mapped[str] = mapped_column(String, default="A5")
    content: Mapped[dict] = mapped_column(JSON)  # data validated as report.v1
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class Run(Scoped, Base):
    """One execution of a scenario or an orchestrated goal (see core/runs.py)."""

    __tablename__ = "run"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    kind: Mapped[str] = mapped_column(String)  # scenario | orchestrate
    workflow: Mapped[str] = mapped_column(String)  # scenario id, or the goal
    scope: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, default="running", index=True)
    thread_id: Mapped[str | None] = mapped_column(String, nullable=True)  # LangGraph thread
    trace_id: Mapped[str | None] = mapped_column(String, nullable=True)  # OpenTelemetry
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    state: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # what a resume needs
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # final trace
    lease_owner: Mapped[str | None] = mapped_column(String, nullable=True)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class WorkflowVersion(Scoped, Base):
    """One saved version of a workflow in a workspace (see core/workflow_store.py).

    The spec never changes once saved; a draft becomes the workflow in use when it is published.
    """

    __tablename__ = "workflow_version"
    __table_args__ = (UniqueConstraint("workspace_id", "workflow_id", "version",
                                       name="uq_workflow_version"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workflow_id: Mapped[str] = mapped_column(String, index=True)
    version: Mapped[int] = mapped_column(Integer)
    spec: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String, default="draft")  # draft | published
    note: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    published_by: Mapped[str | None] = mapped_column(String, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class RunStep(Scoped, Base):
    """One agent's work inside a run."""

    __tablename__ = "run_step"
    __table_args__ = (UniqueConstraint("run_id", "seq", name="uq_run_step_run_id_seq"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("run.id"), index=True)
    seq: Mapped[int] = mapped_column(Integer)
    agent: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, default="running")
    attempts: Mapped[int] = mapped_column(Integer, default=1)
    output_schemas: Mapped[list] = mapped_column(JSON, default=list)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # reused on resume
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class AgentMessageRow(Scoped, Base):
    """Immutable (append-only) log of §4 messages, for audit and reproducibility."""

    __tablename__ = "agent_message"
    message_id: Mapped[str] = mapped_column(String, primary_key=True)
    sender: Mapped[str] = mapped_column(String)
    receiver: Mapped[str] = mapped_column(String)
    intent: Mapped[str] = mapped_column(String)
    task_ref: Mapped[str] = mapped_column(String)
    payload: Mapped[dict] = mapped_column(JSON)
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    human_gate_required: Mapped[bool] = mapped_column(Boolean, default=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    run_id: Mapped[str | None] = mapped_column(
        ForeignKey("run.id", name="fk_agent_message_run_id"), nullable=True, index=True
    )
    # set inside a run step: a retried step cannot write the same row twice
    dedupe_key: Mapped[str | None] = mapped_column(String, nullable=True, unique=True, index=True)


class Approval(Scoped, Base):
    __tablename__ = "approval"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    message_id: Mapped[str] = mapped_column(ForeignKey("agent_message.message_id"))
    approver: Mapped[str | None] = mapped_column(String, nullable=True)
    # pending | approve | reject | cancelled (its run ended first)
    decision: Mapped[str] = mapped_column(String, default="pending")
    decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    run_id: Mapped[str | None] = mapped_column(
        ForeignKey("run.id", name="fk_approval_run_id"), nullable=True, index=True
    )


class KnowledgeDoc(Scoped, Base):
    """Knowledge / lessons-learned corpus (A7 RAG). Lightweight: for local lexical search.

    `title`/`text` are English; `translations` holds other languages, e.g.
    {"ko": {"title": ..., "text": ...}}. In production, add a pgvector/Qdrant embedding
    column (see connectors/vectordb.py).
    """

    __tablename__ = "knowledge_doc"
    __table_args__ = (_key(),)
    id: Mapped[str] = mapped_column(String)
    project_ref: Mapped[str] = mapped_column(String, default="")  # past project
    title: Mapped[str] = mapped_column(String)
    text: Mapped[str] = mapped_column(Text)
    tags: Mapped[list] = mapped_column(JSON, default=list)
    translations: Mapped[dict] = mapped_column(JSON, default=dict)


class KpiEvent(Scoped, Base):
    """Five-axis telemetry (§7). axis ∈ {time,resource,delivery,risk,cost}."""

    __tablename__ = "kpi_event"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    axis: Mapped[str] = mapped_column(String)
    metric: Mapped[str] = mapped_column(String)
    value: Mapped[float] = mapped_column(Float)
    project_id: Mapped[str | None] = mapped_column(String, nullable=True)
    meta: Mapped[dict] = mapped_column(JSON, default=dict)
    ts: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    run_id: Mapped[str | None] = mapped_column(
        ForeignKey("run.id", name="fk_kpi_event_run_id"), nullable=True, index=True
    )
    # set inside a run step: a retried step cannot write the same row twice
    dedupe_key: Mapped[str | None] = mapped_column(String, nullable=True, unique=True, index=True)
