"""Run records — what ran, in which steps, and how it ended.

Scenarios and orchestrated goals both execute inside `track(...)`, and each agent inside
`step(...)`. The current run travels in a context variable, so `kpi.record` and
`protocol.publish` link their rows to it without agents knowing about runs. Code outside a
run (a single `POST /plan`, for example) simply records no run id.
"""
from __future__ import annotations

import threading
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import func, select

from ma_pmo.core import tracing
from ma_pmo.db.models import Run, RunStep
from ma_pmo.db.session import get_session

RUNNING, SUCCEEDED, FAILED = "running", "succeeded", "failed"
_MAX_ERROR = 500

_current_run: ContextVar[str | None] = ContextVar("ma_pmo_run", default=None)
_seq_lock = threading.Lock()  # workers of one run can start in parallel


def current_run_id() -> str | None:
    return _current_run.get()


def _now() -> datetime:
    return datetime.now(UTC)


@contextmanager
def track(kind: str, workflow: str, scope: str, *, thread_id: str | None = None) -> Iterator[str]:
    """Record a run around the block. A nested call joins the run already in progress."""
    active = _current_run.get()
    if active is not None:
        yield active
        return
    run_id = uuid.uuid4().hex
    with get_session() as s:
        s.add(Run(id=run_id, kind=kind, workflow=workflow[:500], scope=scope, status=RUNNING,
                  thread_id=thread_id, trace_id=tracing.current_trace_id()))
    token = _current_run.set(run_id)
    try:
        yield run_id
    except Exception as e:
        _finish_run(run_id, FAILED, str(e)[:_MAX_ERROR])
        raise
    else:
        _finish_run(run_id, SUCCEEDED)
    finally:
        _current_run.reset(token)


def _finish_run(run_id: str, status: str, error: str | None = None) -> None:
    with get_session() as s:
        run = s.get(Run, run_id)
        if run is not None:
            run.status, run.error, run.finished_at = status, error, _now()


@dataclass
class StepHandle:
    """Filled in by the caller while the step runs."""

    output_schemas: list = field(default_factory=list)


@contextmanager
def step(agent: str) -> Iterator[StepHandle]:
    """Record one agent's step in the current run; does nothing outside a run."""
    handle = StepHandle()
    run_id = _current_run.get()
    if run_id is None:
        yield handle
        return
    with _seq_lock, get_session() as s:
        seq = (s.scalar(select(func.max(RunStep.seq)).where(RunStep.run_id == run_id)) or 0) + 1
        row = RunStep(run_id=run_id, seq=seq, agent=agent, status=RUNNING)
        s.add(row)
        s.flush()
        step_id = row.id
    try:
        yield handle
    except Exception as e:
        _finish_step(step_id, FAILED, handle, str(e)[:_MAX_ERROR])
        raise
    else:
        _finish_step(step_id, SUCCEEDED, handle)


def _finish_step(step_id: int, status: str, handle: StepHandle, error: str | None = None) -> None:
    with get_session() as s:
        row = s.get(RunStep, step_id)
        if row is not None:
            row.status, row.error, row.finished_at = status, error, _now()
            row.output_schemas = handle.output_schemas


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _summary(run: Run) -> dict:
    return {
        "run_id": run.id, "kind": run.kind, "workflow": run.workflow, "scope": run.scope,
        "status": run.status, "thread_id": run.thread_id, "trace_id": run.trace_id,
        "error": run.error, "started_at": _iso(run.started_at),
        "finished_at": _iso(run.finished_at),
    }


def list_runs(status: str | None = None, limit: int = 50) -> list[dict]:
    with get_session() as s:
        stmt = select(Run).order_by(Run.started_at.desc()).limit(limit)
        if status:
            stmt = stmt.where(Run.status == status)
        return [_summary(r) for r in s.scalars(stmt).all()]


def get_run(run_id: str) -> dict | None:
    with get_session() as s:
        run = s.get(Run, run_id)
        if run is None:
            return None
        steps = s.scalars(select(RunStep).where(RunStep.run_id == run_id)
                          .order_by(RunStep.seq)).all()
        return {**_summary(run), "steps": [
            {"seq": st.seq, "agent": st.agent, "status": st.status, "attempts": st.attempts,
             "output_schemas": st.output_schemas, "error": st.error,
             "started_at": _iso(st.started_at), "finished_at": _iso(st.finished_at)}
            for st in steps
        ]}
