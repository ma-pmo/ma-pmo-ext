"""Run records — what ran, in which steps, how it ended, and how to continue it.

Scenarios and orchestrated goals execute inside `track(...)`, and each agent inside `step(...)`.
The current run travels in a context variable, so `kpi.record` and `protocol.publish` link their
rows to it without agents knowing about runs. Code outside a run records no run id.

Statuses: running → succeeded | failed, or
- waiting_approval: paused at a gate; approving resumes it, rejecting cancels it
- interrupted: its process died; resume retries the unfinished step
- cancelled: an approval was rejected

Continuing a run is safe to attempt from anywhere. A lease, taken with one atomic UPDATE, gives
a run to a single process; finished steps are not re-run; and rows written in a step carry a
`dedupe_key`, so retrying the step cannot write them twice. Risk and report rows have no key: a
step retried after a crash can add a second one.
"""
from __future__ import annotations

import json
import os
import socket
import threading
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, or_, select, update

from ma_pmo.core import tracing, workspace
from ma_pmo.core.config import get_settings
from ma_pmo.db.models import Approval, Run, RunStep
from ma_pmo.db.session import get_session

RUNNING, SUCCEEDED, FAILED = "running", "succeeded", "failed"
WAITING, INTERRUPTED, CANCELLED = "waiting_approval", "interrupted", "cancelled"
_MAX_ERROR = 500
_OWNER = f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:8]}"

_current_run: ContextVar[str | None] = ContextVar("ma_pmo_run", default=None)
_current_step: ContextVar[StepHandle | None] = ContextVar("ma_pmo_step", default=None)
_seq_lock = threading.Lock()  # workers of one run can start in parallel


class NotResumable(Exception):
    """The run cannot continue now; the message says why."""


def current_run_id() -> str | None:
    return _current_run.get()


def dedupe_key(kind: str) -> str | None:
    """Key for the next row of `kind` in this step: the same on every attempt of the step."""
    handle = _current_step.get()
    if handle is None:
        return None
    handle.written[kind] = handle.written.get(kind, 0) + 1
    return f"{handle.run_id}:{handle.seq}:{kind}:{handle.written[kind]}"


def _now() -> datetime:
    return datetime.now(UTC)


def _lease_until() -> datetime:
    return _now() + timedelta(seconds=get_settings().run_lease_sec)


def _json(value: Any) -> Any:
    """Plain JSON, so dates and enums in agent outputs can be stored."""
    return json.loads(json.dumps(value, default=str, ensure_ascii=False))


@contextmanager
def _supervise(run_id: str) -> Iterator[str]:
    """Make `run_id` current and record how the block ends."""
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


@contextmanager
def track(kind: str, workflow: str, scope: str, *, thread_id: str | None = None,
          state: dict | None = None) -> Iterator[str]:
    """Record a run around the block. A nested call joins the run already in progress."""
    active = _current_run.get()
    if active is not None:
        yield active
        return
    run_id = uuid.uuid4().hex
    with get_session() as s:
        s.add(Run(id=run_id, kind=kind, workflow=workflow[:500], scope=scope, status=RUNNING,
                  thread_id=thread_id, trace_id=tracing.current_trace_id(), state=state,
                  lease_owner=_OWNER, lease_until=_lease_until()))
    with _supervise(run_id):
        yield run_id


def _finish_run(run_id: str, status: str, error: str | None = None) -> None:
    """End a run that is still running; a paused run keeps its status."""
    with get_session() as s:
        run = s.get(Run, run_id)
        if run is not None and run.status == RUNNING:
            run.status, run.error, run.finished_at = status, error, _now()
            run.lease_owner = run.lease_until = None


@dataclass
class StepHandle:
    """Filled in by the caller while the step runs."""

    run_id: str = ""
    seq: int = 0
    output_schemas: list = field(default_factory=list)
    result: dict | None = None  # saved so a resumed run can reuse this step
    written: dict[str, int] = field(default_factory=dict)


@contextmanager
def step(agent: str, seq: int | None = None) -> Iterator[StepHandle]:
    """Record one agent's step in the current run; does nothing outside a run.

    Pass `seq` for a planned position: an unfinished step at that position is retried.
    """
    run_id = _current_run.get()
    if run_id is None:
        yield StepHandle()
        return
    with _seq_lock, get_session() as s:
        if seq is None:
            seq = (s.scalar(select(func.max(RunStep.seq)).where(RunStep.run_id == run_id))
                   or 0) + 1
        row = s.scalar(select(RunStep).where(RunStep.run_id == run_id, RunStep.seq == seq))
        if row is None:
            row = RunStep(run_id=run_id, seq=seq, agent=agent, status=RUNNING)
            s.add(row)
        else:
            row.attempts, row.status, row.error = row.attempts + 1, RUNNING, None
            row.started_at, row.finished_at = _now(), None
        s.flush()
        step_id = row.id
        s.execute(update(Run).where(Run.id == run_id).values(lease_until=_lease_until()))
    handle = StepHandle(run_id=run_id, seq=seq)
    token = _current_step.set(handle)
    try:
        yield handle
    except Exception as e:
        _finish_step(step_id, FAILED, handle, str(e)[:_MAX_ERROR])
        raise
    else:
        _finish_step(step_id, SUCCEEDED, handle)
    finally:
        _current_step.reset(token)


def _finish_step(step_id: int, status: str, handle: StepHandle, error: str | None = None) -> None:
    with get_session() as s:
        row = s.get(RunStep, step_id)
        if row is not None:
            row.status, row.error, row.finished_at = status, error, _now()
            row.output_schemas = _json(handle.output_schemas)
            row.result = _json(handle.result)


# ── pausing and continuing ────────────────────────────────────────────────────

def pending_approvals(run_id: str) -> list[int]:
    with get_session() as s:
        return list(s.scalars(select(Approval.id).where(
            Approval.run_id == run_id, Approval.decision == "pending")).all())


def mark_waiting(run_id: str) -> None:
    with get_session() as s:
        s.execute(update(Run).where(Run.id == run_id, Run.status == RUNNING).values(
            status=WAITING, lease_owner=None, lease_until=None))


def cancel(run_id: str, reason: str) -> None:
    """End a paused run; approvals still pending for it no longer mean anything."""
    with get_session() as s:
        s.execute(update(Run).where(Run.id == run_id, Run.status == WAITING).values(
            status=CANCELLED, error=reason[:_MAX_ERROR], finished_at=_now()))
        s.execute(update(Approval).where(
            Approval.run_id == run_id, Approval.decision == "pending"
        ).values(decision="cancelled"))


def save_result(run_id: str, result: dict) -> None:
    with get_session() as s:
        s.execute(update(Run).where(Run.id == run_id).values(result=_json(result)))


def update_state(run_id: str, **values: Any) -> dict:
    with get_session() as s:
        run = s.get(Run, run_id)
        state = {**(run.state or {}), **_json(values)} if run is not None else {}
        if run is not None:
            run.state = state
        return state


def finished_steps(run_id: str) -> dict[int, dict]:
    """Saved results of the steps a resumed run must not repeat, by position."""
    with get_session() as s:
        rows = s.scalars(select(RunStep).where(
            RunStep.run_id == run_id, RunStep.status == SUCCEEDED)).all()
        return {r.seq: r.result or {} for r in rows}


def claim(run_id: str) -> dict:
    """Take the run for this process, or raise NotResumable. Returns its summary."""
    with get_session() as s:
        run = s.get(Run, run_id)
        if run is None:
            raise KeyError(run_id)
        if not (run.state or {}).get("spec"):
            raise NotResumable("this run stopped before its workflow was saved: start it again")
    if pending_approvals(run_id):
        raise NotResumable("approvals are still pending for this run")
    now = _now()
    with get_session() as s:
        claimed = s.execute(update(Run).where(
            Run.id == run_id,
            or_(Run.status.in_((WAITING, INTERRUPTED)),
                (Run.status == RUNNING) & (Run.lease_until < now)),
        ).values(status=RUNNING, lease_owner=_OWNER, lease_until=_lease_until(), error=None,
                 finished_at=None))
        if claimed.rowcount != 1:  # type: ignore[attr-defined]
            raise NotResumable("the run is finished, or another process holds it")
        return _summary(s.get(Run, run_id))  # type: ignore[arg-type]


@contextmanager
def attach(run_id: str) -> Iterator[str]:
    """Continue a claimed run in this block."""
    with _supervise(run_id):
        yield run_id


def recover_interrupted() -> list[str]:
    """Mark runs whose process died (lease expired) so they can be seen and resumed."""
    now = _now()
    every = {workspace.ALL_WORKSPACES: True}  # a stopped process may have served any workspace
    with get_session() as s:
        stale = s.scalars(select(Run.id).where(Run.status == RUNNING, Run.lease_until < now),
                          execution_options=every).all()
        recovered = []
        for run_id in stale:
            moved = s.execute(update(Run).where(
                Run.id == run_id, Run.status == RUNNING, Run.lease_until < now,
            ).values(status=INTERRUPTED, lease_owner=None, lease_until=None,
                     error="process stopped before the run finished"), execution_options=every)
            if moved.rowcount == 1:  # type: ignore[attr-defined]
                s.execute(update(RunStep).where(
                    RunStep.run_id == run_id, RunStep.status == RUNNING
                ).values(status=INTERRUPTED), execution_options=every)
                recovered.append(run_id)
    return recovered


# ── reading ───────────────────────────────────────────────────────────────────

def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _summary(run: Run) -> dict:
    return {
        "run_id": run.id, "kind": run.kind, "workflow": run.workflow, "scope": run.scope,
        "status": run.status, "thread_id": run.thread_id, "trace_id": run.trace_id,
        "error": run.error, "started_at": _iso(run.started_at),
        "finished_at": _iso(run.finished_at),
    }


def get_state(run_id: str) -> dict:
    with get_session() as s:
        run = s.get(Run, run_id)
        return dict(run.state or {}) if run is not None else {}


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
        return {**_summary(run), "result": run.result, "steps": [
            {"seq": st.seq, "agent": st.agent, "status": st.status, "attempts": st.attempts,
             "output_schemas": st.output_schemas, "error": st.error,
             "started_at": _iso(st.started_at), "finished_at": _iso(st.finished_at)}
            for st in steps
        ]}
