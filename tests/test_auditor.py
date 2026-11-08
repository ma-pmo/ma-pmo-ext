"""A8 Auditor and reviewed workflows: a dedicated reviewer after the decisions of a run."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from ma_pmo.agents import registry
from ma_pmo.agents.auditor import AuditorAgent
from ma_pmo.agents.orchestrator import OrchestratorAgent
from ma_pmo.agents.orchestrator_rules import keyword_route
from ma_pmo.api.main import app
from ma_pmo.core import runs, scenarios
from tests.spike import GATE, VARIANTS, portfolio, reviews, run_on, spec

client = TestClient(app)

# decisions only: nothing in it reads, and nothing reviews, until `review` is on
PLAIN = [
    {"id": "A3", "agent": "A3"},
    {"id": "A4", "agent": "A4", "needs": []},
    {"id": "A6", "agent": "A6", "needs": ["A3", "A4"], "params": {"gate": "G3-execution"}},
    {"id": "A5", "agent": "A5", "needs": ["A6"]},
]


def test_the_auditor_is_registered_but_never_routed():
    assert registry.specs()["A8"].output_schema == "review.v1"
    assert "A8" not in registry.routable()
    assert registry.title("A8") == "Auditor"
    assert "- A8" not in OrchestratorAgent().role_prompt
    assert all(d.agent != "A8" for goal in ("audit the review", "감사 검토 리스크 보고")
               for d in keyword_route(goal).delegations)
    agents = {a["id"] for a in client.get("/agents").json()["agents"]}
    assert "A8" in agents  # a workflow may still use it


def test_review_adds_the_auditor_and_lets_decisions_read():
    reviewed = spec(PLAIN, review=True).with_review()
    steps = {s.id: s for s in reviewed.steps}
    assert [s.id for s in reviewed.steps] == ["A3", "A4", "A6", "A5", "review"]
    assert steps["review"].agent == "A8" and steps["review"].reads == "board"
    assert steps["review"].needs == ["A5"]  # the last step: everything else is earlier
    assert steps["A6"].reads == steps["A5"].reads == "upstream"
    assert steps["A3"].reads == steps["A4"].reads == "isolated"
    assert reviewed.with_review() == reviewed  # applying it twice adds nothing
    assert spec(PLAIN).with_review() == spec(PLAIN)  # off: unchanged
    clash = spec([*PLAIN, {"id": "review", "agent": "A2", "needs": []}], review=True)
    assert clash.with_review().steps[-1].id == "review_2"
    assert set(clash.with_review().steps[-1].needs) == {"A5", "review"}


@pytest.mark.parametrize("name", sorted(VARIANTS))
def test_the_auditor_challenges_what_the_builders_challenge(name, monkeypatch):
    _change, expected, _fixed = VARIANTS[name]
    outputs = run_on(monkeypatch, portfolio(name), spec(PLAIN, review=True))
    dedicated = {r["constraint"]: r for r in reviews(outputs, "A8")
                 if r.get("project_id") == "PROJ-X"}
    builder = {r["constraint"]: r for r in reviews(outputs, "A6")
               if r.get("project_id") == "PROJ-X"}
    assert set(dedicated) == set(builder) == set(GATE)
    assert {c for c, r in dedicated.items() if r["verdict"] == "CHALLENGE"} == expected
    assert {c: r["verdict"] for c, r in dedicated.items()} == \
        {c: r["verdict"] for c, r in builder.items()}
    assert all(r["role"] == "dedicated" for r in reviews(outputs, "A8"))
    gate_ids = {o["data"]["project_id"] for o in outputs if o["schema"] == "gate_review.v1"}
    assert {r.get("project_id") for r in reviews(outputs, "A8") if r.get("project_id")} == gate_ids
    [report] = [r for r in reviews(outputs, "A8") if r["constraint"] == "report.covers_risks"]
    assert report["verdict"] == "VERIFIED"  # A5 already added what was missing


def test_a_dedicated_review_sees_what_a_builder_could_not(monkeypatch):
    narrow = [{**s, "needs": ["A4"]} if s["id"] == "A6" else s for s in PLAIN]
    outputs = run_on(monkeypatch, portfolio("no_skill"), spec(narrow, review=True))
    builder = {r["constraint"]: r["verdict"] for r in reviews(outputs, "A6")
               if r.get("project_id") == "PROJ-X"}
    dedicated = {r["constraint"]: r["verdict"] for r in reviews(outputs, "A8")
                 if r.get("project_id") == "PROJ-X"}
    assert builder == {"gate.no_open_high_risk": "VERIFIED"}  # A6 does not wait for A3
    assert dedicated["gate.staffed"] == "CHALLENGE"  # A8 reads every earlier stage
    assert dedicated["gate.no_open_high_risk"] == "VERIFIED"  # and both verdicts stay


def test_an_isolated_auditor_reviews_nothing():
    assert AuditorAgent().run({"task_ref": "PORTFOLIO#2026-Q1"}) == {"outputs": []}


def test_a_reviewed_scenario_runs_end_to_end_on_the_demo_data():
    flow = scenarios.loaded("risk_escalation").model_copy(update={"review": True})
    trace = scenarios.run_spec(flow)
    assert trace["status"] == "succeeded"
    saved = runs.get_state(trace["run_id"])["spec"]
    assert [s["agent"] for s in saved["steps"]] == ["A4", "A6", "A5", "A8"]
    by_agent = {}
    for m in trace["communications"]:
        if m["schema"] == "review.v1":
            by_agent.setdefault(m["sender"], 0)
            by_agent[m["sender"]] += 1
    assert by_agent.get("A6") and by_agent.get("A5") and by_agent.get("A8")
    graph = client.get(f"/runs/{trace['run_id']}/workflow").json()
    assert graph["steps"][-1]["agent"] == "A8"
    assert graph["steps"][-1]["run"]["status"] == "succeeded" and graph["review"] is True
    assert client.get("/workflows/risk_escalation").json()["review"] is False
