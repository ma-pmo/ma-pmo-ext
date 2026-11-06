"""Pausing at approvals, resuming, and recovering from a killed process."""
from __future__ import annotations

import os
import subprocess
import sys
import textwrap
import threading
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update

from ma_pmo.api.main import app
from ma_pmo.core import hitl, runs
from ma_pmo.core.scenarios import WORKERS, resume_scenario, run_scenario
from ma_pmo.db.models import AgentMessageRow, Approval, KpiEvent, Run
from ma_pmo.db.session import get_session

ROOT = Path(__file__).resolve().parents[1]
client = TestClient(app)
GATED = "risk_escalation"  # A4 (queues an approval) -> A6 -> A5


def _approve_all(run_id: str) -> str | None:
    """Approve until the run stops waiting; a later step may raise another gate."""
    status = None
    while runs.get_run(run_id)["status"] == runs.WAITING:
        for approval_id in runs.pending_approvals(run_id):
            status = hitl.resolve(approval_id, approver="pm", decision="approve").get("run_status")
    return status


def _rows(run_id: str) -> tuple[Counter, Counter]:
    with get_session() as s:
        messages = s.scalars(select(AgentMessageRow).where(AgentMessageRow.run_id == run_id)).all()
        kpis = s.scalars(select(KpiEvent).where(KpiEvent.run_id == run_id)).all()
        return (Counter((m.sender, m.task_ref, m.payload["schema"]) for m in messages),
                Counter((k.metric, k.project_id) for k in kpis))


@pytest.mark.smoke
def test_run_waits_at_a_gate_and_approval_finishes_it():
    trace = run_scenario(GATED, pause_on_gate=True)
    run_id = trace["run_id"]
    assert trace["status"] == "waiting_approval" and trace["pending_approvals"]
    assert [p["phase"] for p in trace["phases"]] == ["plan", "execute"]  # stopped after A4
    assert runs.get_run(run_id)["status"] == runs.WAITING

    assert _approve_all(run_id) == "succeeded"
    run = runs.get_run(run_id)
    assert run["status"] == "succeeded" and run["finished_at"]
    assert [(s["agent"], s["attempts"]) for s in run["steps"]] == [("A4", 1), ("A6", 1), ("A5", 1)]
    assert [p["phase"] for p in run["result"]["phases"]][-2:] == ["complete", "insight"]
    assert run["result"]["phases"][1]["agent"] == "A4"  # the first step's saved work is kept


def test_a_rejection_cancels_the_run_and_its_other_approvals():
    trace = run_scenario(GATED, pause_on_gate=True)
    run_id = trace["run_id"]
    first, *others = trace["pending_approvals"]
    result = hitl.resolve(first, approver="pm", decision="reject")
    assert result["run_status"] == "cancelled"
    run = runs.get_run(run_id)
    assert run["status"] == "cancelled" and "rejected by pm" in run["error"]
    assert [s["agent"] for s in run["steps"]] == ["A4"]  # nothing ran after the gate
    assert runs.pending_approvals(run_id) == []
    with get_session() as s:
        for approval_id in others:
            assert s.get(Approval, approval_id).decision == "cancelled"
    assert client.post(f"/runs/{run_id}/resume").status_code == 409


def test_resume_cannot_skip_a_pending_approval():
    run_id = run_scenario(GATED, pause_on_gate=True)["run_id"]
    response = client.post(f"/runs/{run_id}/resume")
    assert response.status_code == 409 and "pending" in response.json()["detail"]
    assert runs.get_run(run_id)["status"] == runs.WAITING


def test_without_pause_on_gate_nothing_changes():
    trace = run_scenario(GATED)
    assert trace["status"] == "succeeded" and "pending_approvals" not in trace
    assert runs.pending_approvals(trace["run_id"])  # queued, but the run did not wait


def test_a_failing_agent_after_approval_does_not_fail_the_decision(monkeypatch):
    run_id = run_scenario(GATED, pause_on_gate=True)["run_id"]

    def boom(state):
        raise RuntimeError("tracker is down")

    monkeypatch.setattr(WORKERS["A6"], "run", boom)
    pending = runs.pending_approvals(run_id)
    results = [hitl.resolve(a, approver="pm", decision="approve") for a in pending]
    assert results[-1]["decision"] == "approve" and results[-1]["run_status"] == "failed"
    assert "tracker is down" in runs.get_run(run_id)["error"]


def test_scenario_api_pause_and_unknown_runs():
    trace = client.post(f"/scenarios/{GATED}/run?pause_on_gate=true&format=markdown").json()
    assert trace["status"] == "waiting_approval" and "paper_markdown" not in trace
    assert client.post("/runs/nope/resume").status_code == 404
    done = client.post("/scenarios/weekly_status/run").json()
    assert client.post(f"/runs/{done['run_id']}/resume").status_code == 409


def test_orchestrated_runs_say_they_cannot_resume_yet():
    run_id = client.post("/orchestrate", json={"goal": "status report"}).json()["run_id"]
    response = client.post(f"/runs/{run_id}/resume")
    assert response.status_code == 409 and "orchestrated" in response.json()["detail"]


def _expire(run_id: str) -> None:
    past = datetime.now(UTC) - timedelta(seconds=5)
    with get_session() as s:
        s.execute(update(Run).where(Run.id == run_id).values(status="running", lease_until=past))


def test_a_live_lease_blocks_recovery_and_resume():
    with runs.track("scenario", "weekly_status", "S", state={}) as run_id:
        assert run_id not in runs.recover_interrupted()
        with pytest.raises(runs.NotResumable, match="another process"):
            runs.claim(run_id)


def test_only_one_process_can_claim_a_run():
    run_id = run_scenario("weekly_status")["run_id"]
    _expire(run_id)
    won: list[str] = []

    def claim() -> None:
        try:
            runs.claim(run_id)
            won.append("yes")
        except runs.NotResumable:
            pass

    threads = [threading.Thread(target=claim) for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert won == ["yes"]


CRASH = textwrap.dedent("""
    import os
    from ma_pmo.agents import risk
    from ma_pmo.core.scenarios import run_scenario

    real, calls = risk.protocol.publish, []

    def publish_then_die(message):
        if message.payload.schema_ == "risk_alert.v1":
            calls.append(message)
            if len(calls) == 2:  # the second alert of A4: the step is half done
                os._exit(9)
        return real(message)

    risk.protocol.publish = publish_then_die
    run_scenario("quarterly_review")
""")


def test_killed_process_resumes_without_duplicates():
    clean = run_scenario("quarterly_review")
    env = {**os.environ, "PYTHONPATH": str(ROOT), "MA_PMO_RUN_LEASE_SEC": "0"}
    killed = subprocess.run([sys.executable, "-c", CRASH], env=env, capture_output=True,
                            text=True, timeout=120)
    assert killed.returncode == 9, killed.stderr[-500:]
    stuck = runs.list_runs("running", 1)[0]
    run_id = stuck["run_id"]

    assert run_id in runs.recover_interrupted()
    run = runs.get_run(run_id)
    assert run["status"] == "interrupted"
    assert [(s["agent"], s["status"]) for s in run["steps"]] == [
        ("A2", "succeeded"), ("A4", "interrupted")]

    trace = resume_scenario(run_id)
    run = runs.get_run(run_id)
    assert trace["status"] == run["status"] == "succeeded"
    assert [(s["agent"], s["attempts"]) for s in run["steps"]] == [("A2", 1), ("A4", 2), ("A5", 1)]
    assert _rows(run_id) == _rows(clean["run_id"])  # same rows as a run that never crashed
