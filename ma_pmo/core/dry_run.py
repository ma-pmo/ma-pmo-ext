"""Dry run: try a workflow spec on the demo data, and leave nothing behind.

The spec runs in a workspace of its own, created for the run and erased after it, so the real
workspace's data, KPIs and approval queue are never touched. Inside, trackers read the demo data
even when Jira or GitHub is configured, and no notification is sent (`registry.demo_only`).
Agents still call the LLM when one is configured, as a real run would.
"""
from __future__ import annotations

import json
import uuid
from typing import Any

from sqlalchemy import delete

from ma_pmo.core import runs, scenarios, workflow_store, workspace
from ma_pmo.db import workspaces
from ma_pmo.db.init import FIXTURE, load_fixtures, load_lessons
from ma_pmo.db.models import Base, Scoped, Workspace
from ma_pmo.db.session import get_session
from ma_pmo.integrations.registry import demo_only

PREFIX = "dry-run-"


def demo_scope() -> str:
    """The sample portfolio every dry run uses."""
    return str(json.loads(FIXTURE.read_text(encoding="utf-8"))["portfolio"]["id"])


def dry_run(data: dict[str, Any]) -> dict:
    """Validate, then run on demo data. Never raises for a bad spec or a failing agent."""
    spec, found = workflow_store.problems(data)
    if found or spec is None:
        return {"ok": False, "problems": found}
    sandbox = f"{PREFIX}{uuid.uuid4().hex[:12]}"
    workspaces.create(sandbox, "dry run")
    try:
        with workspace.use(sandbox), demo_only():
            load_fixtures()
            load_lessons()
            error = None
            try:
                trace = scenarios.run_spec(spec, demo_scope())
                run_id = trace["run_id"]
            except Exception as e:  # report it like any other result of the run
                error = f"{type(e).__name__}: {e}"
                trace, run_id = {}, runs.list_runs(limit=1)[0]["run_id"]
            states = runs.step_states(run_id)
            return {
                "ok": error is None, "problems": [], "error": error,
                "status": runs.get_run(run_id)["status"],  # type: ignore[index]
                "scope": demo_scope(),
                "steps": [{"id": step.id, "agent": step.agent,
                           **states.get(seq, {"status": "not_started", "pending_approvals": 0})}
                          for seq, step in enumerate(spec.steps, start=1)],
                "approvals": len(runs.pending_approvals(run_id)),
                "messages": len(trace.get("communications", [])),
                "phases": trace.get("phases", []),
            }
    finally:
        _erase(sandbox)


def _erase(sandbox: str) -> None:
    scoped = {m.persist_selectable: m.class_ for m in Base.registry.mappers
              if issubclass(m.class_, Scoped)}
    with workspace.use(sandbox), get_session() as s:
        for table in reversed(Base.metadata.sorted_tables):  # children before parents
            if table in scoped:
                s.execute(delete(scoped[table]))
    with get_session() as s:
        s.execute(delete(Workspace).where(Workspace.id == sandbox))
