"""Dry runs: a draft runs on the demo data and leaves nothing behind."""
from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from ma_pmo.api.main import app
from ma_pmo.core import dry_run, scenarios
from ma_pmo.db import workspaces
from ma_pmo.db.models import AgentMessageRow, Approval, KpiEvent, Run
from ma_pmo.db.session import get_session
from ma_pmo.integrations import registry

client = TestClient(app)


def _counts() -> tuple[int, ...]:
    with get_session() as s:
        return tuple(s.scalar(select(func.count()).select_from(m))
                     for m in (Run, AgentMessageRow, Approval, KpiEvent))


def test_a_dry_run_reports_the_run_and_touches_nothing_real():
    before, spaces = _counts(), workspaces.list_all()
    body = client.post("/workflows/dry-run",
                       json={"spec": scenarios.loaded("risk_escalation").model_dump()}).json()
    assert body["ok"] is True and body["status"] == "succeeded"
    assert body["scope"] == "PORTFOLIO#2026-Q1"
    assert [(s["agent"], s["status"]) for s in body["steps"]] == [
        ("A4", "succeeded"), ("A6", "succeeded"), ("A5", "succeeded")]
    assert body["approvals"] > 0 and body["messages"] > 0
    assert [p["phase"] for p in body["phases"]][-1] == "insight"
    # the real workspace has no new run, message, approval or KPI, and the sandbox is gone
    assert _counts() == before and workspaces.list_all() == spaces


def test_a_draft_that_breaks_a_rule_is_not_run():
    spec = scenarios.loaded("knowledge_kickoff").model_dump()
    spec["steps"] = spec["steps"][:2]  # drops the required gate
    before = _counts()
    body = client.post("/workflows/dry-run", json={"spec": spec}).json()
    assert body["ok"] is False and "cannot be removed" in body["problems"][0]
    assert _counts() == before


def test_a_failing_agent_is_reported_not_raised(monkeypatch):
    from ma_pmo.agents.registry import WORKERS

    def boom(state):
        raise RuntimeError("tracker is down")

    monkeypatch.setattr(WORKERS["A5"], "run", boom)
    before, spaces = _counts(), workspaces.list_all()
    body = dry_run.dry_run(scenarios.loaded("weekly_status").model_dump())
    assert body["ok"] is False and "tracker is down" in body["error"]
    assert body["status"] == "failed"
    assert [s["status"] for s in body["steps"]][-1] == "failed"
    assert _counts() == before and workspaces.list_all() == spaces


def test_trackers_read_demo_data_and_nothing_is_sent_during_a_dry_run(monkeypatch):
    seen: list[str] = []

    class RealTracker:
        def get_portfolio_status(self, portfolio_id):
            seen.append(portfolio_id)
            return {"portfolio_id": portfolio_id, "found": True, "projects": []}

    sent: list = []

    class Notifier:
        def send(self, event):
            sent.append(event)

    monkeypatch.setattr(registry, "_active", lambda kind, settings: [type("S", (), {
        "name": kind, "factory": staticmethod(
            lambda s: RealTracker() if kind == "tracker" else Notifier())})()])
    tracker = registry.get_tracker()
    tracker.get_portfolio_status("live")
    with registry.demo_only():
        assert tracker.get_portfolio_status("PORTFOLIO#2026-Q1")["projects"]  # demo data
    assert seen == ["live"]
    body = dry_run.dry_run(scenarios.loaded("risk_escalation").model_dump())
    assert body["ok"] and sent == []
