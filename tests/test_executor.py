"""The one executor: dependencies, parallel steps, joins, pausing, and goals resuming."""
from __future__ import annotations

import os
import subprocess
import sys
import textwrap
import threading
from collections import Counter
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel
from sqlalchemy import select

from ma_pmo.agents import registry
from ma_pmo.agents.registry import WORKERS
from ma_pmo.api.main import app
from ma_pmo.core import executor, hitl, runs
from ma_pmo.core.goals import run_goal, workflow_for
from ma_pmo.core.scenarios import run_scenario
from ma_pmo.core.workflow import WorkflowSpec
from ma_pmo.db.models import AgentMessageRow
from ma_pmo.db.session import get_session
from ma_pmo.sdk import BaseAgent

ROOT = Path(__file__).resolve().parents[1]
client = TestClient(app)
TEXT = {"en": "x", "ko": "x"}
SCOPE = "PORTFOLIO#2026-Q1"


class Out(BaseModel):
    text: str


class Recorder(BaseAgent[Out]):
    """Stands in for a worker and notes the order things happen in."""

    def __init__(self, name: str, log: list[str], barrier: threading.Barrier | None = None):
        self.agent_id, self.name, self.log, self.barrier = name, name, log, barrier

    def run(self, state):
        self.log.append(f"start {self.name}")
        if self.barrier:
            self.barrier.wait(timeout=10)  # only passes if the other step is running too
        self.log.append(f"end {self.name}")
        return {"outputs": [{"agent": self.name, "schema": "x.v1", "data": {"text": self.name}}]}


@pytest.fixture
def workers(monkeypatch):
    """Replace workers A2..A7 with recorders; returns the shared log."""
    log: list[str] = []

    def install(barrier_for: tuple[str, ...] = ()) -> list[str]:
        barrier = threading.Barrier(len(barrier_for)) if barrier_for else None
        fake = {a: Recorder(a, log, barrier if a in barrier_for else None)
                for a in registry.worker_ids()}
        monkeypatch.setattr(registry, "_instances", fake)
        return log

    return install


def _run(steps, **kwargs) -> tuple[str, executor.Outcome]:
    spec = WorkflowSpec.model_validate(
        {"id": "t", "title": TEXT, "goal": TEXT, "description": TEXT, "steps": steps})
    with runs.track("scenario", "t", SCOPE, state={"spec": spec.model_dump()}) as run_id:
        return run_id, executor.execute(run_id, spec, SCOPE, "goal", **kwargs)


@pytest.mark.smoke
def test_independent_steps_run_in_parallel_and_a_join_waits_for_both(workers):
    log = workers(barrier_for=("A2", "A4"))  # A2 and A4 must be inside run() at the same time
    run_id, outcome = _run([
        {"id": "a", "agent": "A2", "needs": []},
        {"id": "b", "agent": "A4", "needs": []},
        {"id": "join", "agent": "A5", "needs": ["a", "b"]},
    ])
    assert log.index("start A5") > max(log.index("end A2"), log.index("end A4"))
    assert [o["agent"] for o in outcome.outputs] == ["A2", "A4", "A5"]  # workflow order
    assert [s["status"] for s in runs.get_run(run_id)["steps"]] == ["succeeded"] * 3


def test_needs_decide_the_order_not_the_list(workers):
    log = workers()
    _run([{"id": "last", "agent": "A5", "needs": ["first"]},
          {"id": "first", "agent": "A2", "needs": []}])
    assert log == ["start A2", "end A2", "start A5", "end A5"]


def test_a_diamond_runs_each_step_once(workers):
    log = workers()
    _run([{"id": "top", "agent": "A2", "needs": []},
          {"id": "left", "agent": "A3", "needs": ["top"]},
          {"id": "right", "agent": "A4", "needs": ["top"]},
          {"id": "bottom", "agent": "A5", "needs": ["left", "right"]}])
    assert Counter(x for x in log if x.startswith("start")) == Counter(
        {"start A2": 1, "start A3": 1, "start A4": 1, "start A5": 1})
    assert log[0] == "start A2" and log[-1] == "end A5"


def test_more_steps_than_the_default_recursion_limit(workers):
    workers()
    steps = [{"id": f"s{i}", "agent": "A2"} for i in range(40)]
    _, outcome = _run(steps)
    assert len(outcome.outputs) == 40


def test_ablation_keeps_the_rest_connected():
    spec = WorkflowSpec.model_validate({
        "id": "t", "title": TEXT, "goal": TEXT, "description": TEXT,
        "steps": [{"id": "a", "agent": "A2", "needs": []},
                  {"id": "b", "agent": "A4", "needs": ["a"]},
                  {"id": "c", "agent": "A5", "needs": ["a", "b"]}]})
    assert spec.without_agents(["A4"]).dependencies() == {"a": [], "c": ["a"]}


def test_a_scenario_with_every_agent_removed_still_ends():
    trace = run_scenario("weekly_status", drop_agents=("A2", "A5"))
    assert trace["status"] == "succeeded"
    assert [p["phase"] for p in trace["phases"]] == ["plan", "complete", "insight"]


def test_goal_becomes_a_parallel_workflow():
    routing = {"delegations": [{"agent": "A4", "task": "risks"}, {"agent": "A5", "task": "report"},
                               {"agent": "A4", "task": "again"}]}
    spec = workflow_for("g", routing)
    assert spec.dependencies() == {"A4": [], "A5": []}  # repeated delegation runs once
    assert spec.steps[0].params == {"task": "risks"}


def test_a_failing_step_fails_the_goal_and_is_recorded(monkeypatch):
    def boom(state):
        raise RuntimeError("tracker is down")

    monkeypatch.setattr(WORKERS["A4"], "run", boom)
    with pytest.raises(RuntimeError, match="tracker is down"):
        run_goal("risk check", SCOPE)
    failed = runs.list_runs("failed", 1)[0]
    assert failed["kind"] == "orchestrate" and "tracker is down" in failed["error"]


@pytest.mark.smoke
def test_goal_waits_for_approval_then_synthesizes():
    body = client.post("/orchestrate", json={"goal": "risk review", "pause_on_gate": True}).json()
    assert body["status"] == "waiting_approval" and body["synthesis"] is None
    run_id = body["run_id"]
    assert client.post(f"/runs/{run_id}/resume").status_code == 409  # approvals come first
    status = None
    for approval_id in body["pending_approvals"]:
        status = hitl.resolve(approval_id, approver="pm", decision="approve").get("run_status")
    assert status == "succeeded"
    run = runs.get_run(run_id)
    assert run["result"]["synthesis"]["summary"] and run["result"]["status"] == "succeeded"
    assert all(s["attempts"] == 1 for s in run["steps"])


def test_rejecting_cancels_a_goal():
    body = run_goal("risk review", SCOPE, pause_on_gate=True)
    result = hitl.resolve(body["pending_approvals"][0], approver="pm", decision="reject")
    assert result["run_status"] == "cancelled"
    assert runs.get_run(body["run_id"])["result"] is None


def test_nothing_new_starts_while_an_approval_is_pending(workers, monkeypatch):
    log = workers()
    monkeypatch.setattr(runs, "pending_approvals", lambda run_id: [1])
    run_id, outcome = _run([{"id": "a", "agent": "A2", "needs": []},
                            {"id": "b", "agent": "A5", "needs": ["a"]}], pause_on_gate=True)
    assert outcome.paused and log == []
    assert runs.get_run(run_id)["status"] == runs.WAITING


CRASH = textwrap.dedent("""
    import os
    from ma_pmo.agents.registry import WORKERS
    from ma_pmo.core.goals import run_goal

    worker = WORKERS["A5"]
    real = worker.run

    def run_then_die(state):
        real(state)
        os._exit(9)  # the step did its work but never reported it

    worker.run = run_then_die
    run_goal("risk and schedule report", "PORTFOLIO#2026-Q1", thread_id="crash-test")
""")


def test_killed_goal_resumes_without_duplicates():
    env = {**os.environ, "PYTHONPATH": str(ROOT), "MA_PMO_RUN_LEASE_SEC": "0"}
    killed = subprocess.run([sys.executable, "-c", CRASH], env=env, capture_output=True,
                            text=True, timeout=120)
    assert killed.returncode == 9, killed.stderr[-500:]
    stuck = next(r for r in runs.list_runs("running", 5) if r["thread_id"] == "crash-test")
    run_id = stuck["run_id"]
    assert run_id in runs.recover_interrupted()

    result = client.post(f"/runs/{run_id}/resume").json()
    assert result["status"] == "succeeded" and result["synthesis"]["summary"]
    assert {o["agent"] for o in result["outputs"]} == {"A2", "A4", "A5"}
    with get_session() as s:
        keys = s.scalars(select(AgentMessageRow.dedupe_key).where(
            AgentMessageRow.run_id == run_id)).all()
    assert len(keys) == len(set(keys)) and sum(k.endswith(":message:1") for k in keys) == 3
    reports = [m for m in result["outputs"] if m["agent"] == "A5"]
    assert len(reports) == 1
