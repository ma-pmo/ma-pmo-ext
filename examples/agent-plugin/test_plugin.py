"""Runs in CI with this package installed next to MA-PMO, as a user would have it."""
from pathlib import Path

from ma_pmo_budget_agent import SPEC

from ma_pmo.agents import registry
from ma_pmo.agents.orchestrator_rules import keyword_route
from ma_pmo.core import hitl, scenarios
from ma_pmo.core.goals import run_goal
from ma_pmo.sdk.testing import assert_agent_contract


def test_contract():
    result = assert_agent_contract(SPEC)
    assert {o["data"]["project_id"] for o in result["outputs"]} == {"PROJ-14", "PROJ-22", "PROJ-31"}


def test_found_through_its_entry_point():
    assert registry.problems() == []
    assert registry.specs()["acme.budget"].source == "ma-pmo-budget-agent"


def test_routed_and_run_for_a_goal():
    assert [d.agent for d in keyword_route("남은 예산 알려줘").delegations] == ["acme.budget"]
    final = run_goal("budget check", "PORTFOLIO#2026-Q1")
    assert {o["schema"] for o in final["outputs"]} == {"acme_budget.v1"}


def test_over_limit_goes_to_a_person(monkeypatch):
    monkeypatch.setenv("ACME_PROJECT_LIMIT", "1")
    assert_agent_contract(SPEC)
    assert any(a["sender"] == "acme.budget" for a in hitl.list_pending())


def test_runs_in_a_workflow_file():
    assert scenarios.reload_workflows(str(Path(__file__).parent / "workflows")) == []
    trace = scenarios.run_scenario("budget_review")
    assert [p["agent"] for p in trace["phases"] if p["phase"] == "execute"] == ["acme.budget", "A5"]
