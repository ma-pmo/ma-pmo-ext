"""The workflow a run used, with where each step stands: what the workflow view overlays."""
from __future__ import annotations

from fastapi.testclient import TestClient

from ma_pmo.api.main import app
from ma_pmo.core import hitl, runs, scenarios
from ma_pmo.core.goals import run_goal
from ma_pmo.core.scenarios import run_scenario

client = TestClient(app)
GATED = "risk_escalation"  # A4 (queues an approval) -> A6 -> A5


def _states(run_id: str) -> list[tuple[str, str, int]]:
    body = client.get(f"/runs/{run_id}/workflow").json()
    return [(s["agent"], s["run"]["status"], s["run"]["pending_approvals"]) for s in body["steps"]]


def test_a_paused_run_shows_the_waiting_step_and_what_has_not_started():
    run_id = run_scenario(GATED, pause_on_gate=True)["run_id"]
    body = client.get(f"/runs/{run_id}/workflow").json()
    assert body["run"]["status"] == "waiting_approval" and body["same_as_current"] is True
    assert body["id"] == GATED and "steps" not in body["run"]
    pending = len(runs.pending_approvals(run_id))
    assert _states(run_id) == [("A4", "succeeded", pending), ("A6", "not_started", 0),
                               ("A5", "not_started", 0), ("A8", "not_started", 0)]  # reviewed
    assert pending > 0

    while runs.get_run(run_id)["status"] == runs.WAITING:
        for approval_id in runs.pending_approvals(run_id):
            hitl.resolve(approval_id, approver="pm", decision="approve")
    assert [s for _, s, _ in _states(run_id)] == ["succeeded"] * 4
    assert all(n == 0 for _, _, n in _states(run_id))


def test_a_run_keeps_showing_the_workflow_it_used(monkeypatch):
    run_id = run_scenario("weekly_status")["run_id"]
    current = scenarios.workflow("weekly_status")
    changed = current.model_copy(update={"version": current.version + 1})
    monkeypatch.setitem(scenarios._SPECS, "weekly_status", changed)
    body = client.get(f"/runs/{run_id}/workflow").json()
    assert body["same_as_current"] is False and body["version"] == current.version


def test_goals_and_unknown_runs():
    run_id = run_goal("risk review", "PORTFOLIO#2026-Q1")["run_id"]
    body = client.get(f"/runs/{run_id}/workflow").json()
    assert body["id"] == "goal" and body["same_as_current"] is False
    assert {s["run"]["status"] for s in body["steps"]} == {"succeeded"}
    missing = client.get("/runs/nope/workflow", params={"lang": "ko"})
    assert missing.status_code == 404 and "저장된 워크플로" in missing.json()["detail"]


def test_runs_can_be_listed_for_one_workflow():
    run_id = run_scenario("weekly_status")["run_id"]
    listed = client.get("/runs", params={"workflow": "weekly_status"}).json()
    assert listed[0]["run_id"] == run_id
    assert {r["workflow"] for r in listed} == {"weekly_status"}
