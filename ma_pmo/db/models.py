"""SQLAlchemy data models — paper §6.

Lightweight first (SQLite); the same models work unchanged on Postgres in production.
"""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class Portfolio(Base):
    __tablename__ = "portfolio"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String)
    period: Mapped[str] = mapped_column(String)  # e.g. 2026-Q1
    plan_start: Mapped[str | None] = mapped_column(String, nullable=True)  # ISO week, e.g. 2026-W03

    projects: Mapped[list[Project]] = relationship(back_populates="portfolio")


class Project(Base):
    __tablename__ = "project"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    portfolio_id: Mapped[str] = mapped_column(ForeignKey("portfolio.id"))
    skill: Mapped[str] = mapped_column(String, default="")
    planned_start: Mapped[str | None] = mapped_column(String, nullable=True)
    planned_finish: Mapped[str | None] = mapped_column(String, nullable=True)
    deadline: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, default="green")  # green|amber|red

    portfolio: Mapped[Portfolio] = relationship(back_populates="projects")
    tasks: Mapped[list[Task]] = relationship(back_populates="project")


class Task(Base):
    __tablename__ = "task"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("project.id"))
    wbs: Mapped[str] = mapped_column(String, default="")
    effort: Mapped[float] = mapped_column(Float, default=0.0)
    deps: Mapped[list] = mapped_column(JSON, default=list)  # task_id[]
    percent_complete: Mapped[float] = mapped_column(Float, default=0.0)

    project: Mapped[Project] = relationship(back_populates="tasks")


class Resource(Base):
    __tablename__ = "resource"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    skill: Mapped[str] = mapped_column(String, default="")
    capacity: Mapped[float] = mapped_column(Float, default=40.0)  # hours per week


class Allocation(Base):
    __tablename__ = "allocation"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("project.id"))
    resource_id: Mapped[str] = mapped_column(ForeignKey("resource.id"))
    week: Mapped[str] = mapped_column(String)
    hours: Mapped[float] = mapped_column(Float, default=0.0)


class Risk(Base):
    __tablename__ = "risk"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("project.id"))
    signal: Mapped[str] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(String, default="medium")
    detected_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    materialized_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    mitigation: Mapped[str] = mapped_column(Text, default="")


class Report(Base):
    __tablename__ = "report"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    scope: Mapped[str] = mapped_column(String)
    generated_by: Mapped[str] = mapped_column(String, default="A5")
    content: Mapped[dict] = mapped_column(JSON)  # data validated as report.v1
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class Run(Base):
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


class RunStep(Base):
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


class AgentMessageRow(Base):
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


class Approval(Base):
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


class KnowledgeDoc(Base):
    """Knowledge / lessons-learned corpus (A7 RAG). Lightweight: for local lexical search.

    `title`/`text` are English; `translations` holds other languages, e.g.
    {"ko": {"title": ..., "text": ...}}. In production, add a pgvector/Qdrant embedding
    column (see connectors/vectordb.py).
    """

    __tablename__ = "knowledge_doc"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    project_ref: Mapped[str] = mapped_column(String, default="")  # past project
    title: Mapped[str] = mapped_column(String)
    text: Mapped[str] = mapped_column(Text)
    tags: Mapped[list] = mapped_column(JSON, default=list)
    translations: Mapped[dict] = mapped_column(JSON, default=dict)


class KpiEvent(Base):
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
