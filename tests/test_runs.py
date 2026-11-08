"""Run records: both execution paths are recorded, and rows link back to their run."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text

from ma_pmo.agents.registry import WORKERS
from ma_pmo.api.main import app
from ma_pmo.core import kpi, runs
from ma_pmo.core.scenarios import run_scenario
from ma_pmo.db import migrate
from ma_pmo.db.models import AgentMessageRow, Approval, KpiEvent
from ma_pmo.db.session import get_session

client = TestClient(app)


@pytest.mark.smoke
def test_scenario_run_is_recorded_with_its_steps():
    trace = run_scenario("quarterly_review")
    run = runs.get_run(trace["run_id"])
    assert (run["kind"], run["workflow"], run["status"]) == (
        "scenario", "quarterly_review", "succeeded")
    assert run["finished_at"] and run["error"] is None
    assert [(s["seq"], s["agent"], s["status"]) for s in run["steps"]] == [
        (1, "A2", "succeeded"), (2, "A4", "succeeded"), (3, "A5", "succeeded"),
        (4, "A8", "succeeded")]  # every run is reviewed by default
    assert "schedule.v1" in run["steps"][0]["output_schemas"]


def test_messages_kpis_and_approvals_link_to_the_run():
    run_id = run_scenario("risk_escalation")["run_id"]  # A4 + failed gate queue approvals
    with get_session() as s:
        messages = s.scalars(select(AgentMessageRow).where(AgentMessageRow.run_id == run_id)).all()
        kpis = s.scalars(select(KpiEvent).where(KpiEvent.run_id == run_id)).all()
        approvals = s.scalars(select(Approval).where(Approval.run_id == run_id)).all()
    assert messages and kpis and approvals


def test_work_outside_a_run_has_no_run_id():
    assert runs.current_run_id() is None
    kpi.record("time", "lab_metric_outside_run", 1)
    with get_session() as s:
        row = s.scalars(select(KpiEvent).where(KpiEvent.metric == "lab_metric_outside_run")).one()
    assert row.run_id is None
    with runs.step("A2") as step:  # a step outside a run records nothing and still works
        step.output_schemas = ["x"]


def test_failed_agent_marks_step_and_run_failed(monkeypatch):
    def boom(state):
        raise RuntimeError("tracker is down")

    monkeypatch.setattr(WORKERS["A4"], "run", boom)
    with pytest.raises(RuntimeError, match="tracker is down"):
        run_scenario("quarterly_review")
    failed = runs.list_runs("failed", 1)[0]
    assert failed["workflow"] == "quarterly_review" and "tracker is down" in failed["error"]
    steps = runs.get_run(failed["run_id"])["steps"]
    assert [(s["agent"], s["status"]) for s in steps] == [("A2", "succeeded"), ("A4", "failed")]
    assert runs.current_run_id() is None  # the context is clean after a failure


def test_orchestrated_goal_is_recorded_including_parallel_workers():
    body = client.post("/orchestrate", json={"goal": "Q1 portfolio report with risks"}).json()
    run = runs.get_run(body["run_id"])
    assert run["kind"] == "orchestrate" and run["status"] == "succeeded"
    assert run["thread_id"] == body["thread_id"]
    delegated = {d["agent"] for d in body["routing"]["delegations"]}
    assert delegated and {s["agent"] for s in run["steps"]} == delegated
    assert sorted(s["seq"] for s in run["steps"]) == list(range(1, len(run["steps"]) + 1))
    with get_session() as s:  # context reaches the worker threads
        linked = s.scalars(select(AgentMessageRow).where(
            AgentMessageRow.run_id == body["run_id"])).all()
    assert linked


def test_nested_track_joins_the_active_run():
    with runs.track("scenario", "outer", "S") as outer, runs.track("scenario", "in", "S") as inner:
        assert inner == outer


def test_runs_api():
    run_id = run_scenario("weekly_status")["run_id"]
    assert client.get(f"/runs/{run_id}").json()["steps"]
    assert any(r["run_id"] == run_id for r in client.get("/runs?status=succeeded").json())
    assert client.get("/runs/nope").status_code == 404


def test_upgrade_keeps_existing_rows_and_downgrade_works(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'm.db'}")
    migrate.upgrade(engine, migrate.BASELINE)
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO kpi_event (axis, metric, value, meta, ts) "
                          "VALUES ('time', 'old', 1, '{}', '2026-01-01 00:00:00')"))
    migrate.upgrade(engine)
    with engine.connect() as conn:
        assert conn.execute(text("SELECT metric, run_id FROM kpi_event")).one() == ("old", None)
    migrate.downgrade(engine, migrate.BASELINE)
    assert migrate.current(engine) == migrate.BASELINE
