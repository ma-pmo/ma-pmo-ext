"""Roadmap 9, step 3: an agent asks a person for a missing fact; only its step waits."""
from __future__ import annotations

import copy
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

from ma_pmo.agents import registry
from ma_pmo.agents.planning import PlanningAgent
from ma_pmo.api.main import app
from ma_pmo.core import commitments, questions, runs, scenarios
from ma_pmo.core.config import get_settings
from ma_pmo.core.workflow import WorkflowSpec
from ma_pmo.db.models import Commitment
from ma_pmo.db.session import get_session
from ma_pmo.eval.review import StandInTracker
from ma_pmo.integrations.registry import get_tracker

client = TestClient(app)
TEXT = {"en": "questions", "ko": "질문"}
# A2 plans, A4 rates risk on its own, A5 reports on A2's plan
SPEC = WorkflowSpec.model_validate({
    "id": "questions_test", "title": TEXT, "goal": TEXT, "description": TEXT, "review": False,
    "steps": [{"id": "A2", "agent": "A2"}, {"id": "A4", "agent": "A4", "needs": []},
              {"id": "A5", "agent": "A5", "needs": ["A2"]}]})


@pytest.fixture(autouse=True)
def _no_start_date(monkeypatch):
    """PROJ-22 has no start date; A2 reads this portfolio."""
    monkeypatch.setattr(get_settings(), "report_as_of", "2026-02-16")
    status = copy.deepcopy(get_tracker().get_portfolio_status("PORTFOLIO#2026-Q1"))
    for p in status["projects"]:
        if p["project_id"] == "PROJ-22":
            p.pop("planned_start", None)
    monkeypatch.setitem(registry._instances, "A2", PlanningAgent(StandInTracker(status)))
    yield
    with get_session() as s:
        s.execute(delete(Commitment))


def _plan(run_id: str) -> dict:
    """A2's schedule for PROJ-22 in this run."""
    return next(o for step in runs.finished_steps(run_id).values() for o in step["outputs"]
                if o["schema"] == "schedule.v1" and o["data"]["project_id"] == "PROJ-22")


def _asked() -> tuple[dict, dict]:
    trace = scenarios.run_spec(SPEC)
    (question,) = questions.list_open(trace["run_id"])
    return trace, question


def test_only_the_asking_step_and_what_needs_it_wait():
    trace, question = _asked()
    assert trace["status"] == "input_required"
    assert runs.get_run(trace["run_id"])["status"] == "input_required"
    agents = [p["agent"] for p in trace["phases"] if p.get("phase") == "execute"]
    assert agents == ["A4"]  # A4 went on; A2 asked, and A5 waits for A2
    assert (question["kind"], question["debtor"], question["creditor"]) == (
        "question", "PROJ-22", "A2")
    assert question["check"]["key"] == "PROJ-22.planned_start"
    assert question["check"]["default"] == "2026-02-16"
    assert question["due"].startswith("2026-02-19")  # three days to answer
    thread = client.get(f"/messages/{question['source_message']}/thread").json()
    asked = next(m for m in thread["messages"] if m["schema"] == "question.v1")
    assert asked["sender"] == "A2" and asked["receiver"] == "PROJ-22"


def test_an_answer_resumes_the_run_with_it():
    trace, question = _asked()
    bad = client.post(f"/questions/{question['id']}/answer", json={"value": "soon"})
    assert bad.status_code == 400
    done = client.post(f"/questions/{question['id']}/answer",
                       json={"by": "owner", "value": "2026-01-12"}).json()
    assert done["answer"] == "2026-01-12" and done["run_status"] == "succeeded"
    result = runs.get_run(trace["run_id"])["result"]
    agents = [p["agent"] for p in result["phases"] if p.get("phase") == "execute"]
    assert sorted(agents) == ["A2", "A4", "A5"]
    plan = _plan(trace["run_id"])
    assert plan["data"]["tasks"][0]["early_start"] == "2026-01-12" and "unconfirmed" not in plan
    assert commitments.get(question["id"])["state"] == "satisfied"
    assert client.post(f"/questions/{question['id']}/answer",
                       json={"value": "2026-01-12"}).status_code == 400


def test_no_answer_in_time_uses_the_default_and_marks_it_unconfirmed():
    trace, question = _asked()
    out = commitments.sweep(datetime(2026, 2, 20))
    assert question["id"] in out["violated"] and question["id"] in out["escalated"]
    run = runs.get_run(trace["run_id"])
    assert run["status"] == "succeeded"
    plan = _plan(trace["run_id"])
    assert plan["unconfirmed"] == ["PROJ-22.planned_start"]
    assert plan["data"]["tasks"][0]["early_start"] == "2026-02-16"  # the as-of date
    # the chain for a question tells the person asked and the accountable one; no reopening
    commitments.sweep(datetime(2026, 2, 20) + timedelta(days=30))
    steps = [h.get("step") for h in commitments.get(question["id"])["history"]
             if h["op"] == "escalate"]
    assert steps == ["debtor", "accountable"]


def test_an_agent_asks_only_for_facts_on_its_list():
    with pytest.raises(ValueError, match="not on its list"):
        questions.require({}, "A2", [questions.Question(
            key="PROJ-1.budget", ask="?", why="?", answer_type="value", default=0)])
    assert questions.require({"answers": {"P.planned_start": "2026-01-01"}}, "A2", [
        questions.Question(key="P.planned_start", ask="?", why="?", answer_type="date",
                           default=None)]) == {"P.planned_start": "2026-01-01"}
