"""Dry run: try a workflow spec on the demo data, and leave nothing behind.

The spec runs in a throwaway workspace (core/sandbox.py), so the real workspace's data, KPIs and
approval queue are never touched; trackers read the demo data even when Jira or GitHub is
configured, and no notification is sent. Agents still call the LLM when one is configured, as a
real run would: that spend stays in this workspace's cost ledger (`purpose` "dry_run"), and the
workspace's budgets apply.
"""
from __future__ import annotations

from typing import Any

from ma_pmo.core import runs, scenarios, workflow_store
from ma_pmo.core.i18n import tr
from ma_pmo.core.obs import get_logger
from ma_pmo.core.sandbox import demo_scope, sandbox

_log = get_logger("dry_run")


def dry_run(data: dict[str, Any]) -> dict:
    """Validate, then run on demo data. Never raises for a bad spec or a failing agent."""
    spec, found = workflow_store.problems(data)
    if found or spec is None:
        return {"ok": False, "problems": found}
    with sandbox("dry_run"):
        error = None
        try:
            trace = scenarios.run_spec(spec, demo_scope())
            run_id = trace["run_id"]
        except Exception:  # report it like any other result of the run
            # details go to the log; the failed step's own error is in `steps`, as in a run
            _log.exception("dry_run_failed", workflow=spec.id)
            error = tr("the dry run stopped at a failing step",
                       "시험 실행이 실패한 단계에서 멈췄습니다")
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
            "budget_fallback": trace.get("budget_fallback"),
        }
