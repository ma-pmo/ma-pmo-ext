"""Regression tests — pin results on the bundled demo portfolio that should only change on
purpose. If one fails after a change, either fix the change or update the expected value
in the same PR and say why."""
from __future__ import annotations

import pytest

from ma_pmo.agents.allocation import allocate
from ma_pmo.agents.gates import evaluate_gate
from ma_pmo.agents.orchestrator_rules import keyword_route
from ma_pmo.connectors.jira_mock import MockJiraConnector
from ma_pmo.core.scenarios import SCENARIOS, list_scenarios
from ma_pmo.eval.harness import h3_risk_detection

pytestmark = pytest.mark.regression

SCOPE = "PORTFOLIO#2026-Q1"


@pytest.fixture(scope="module")
def portfolio():
    return MockJiraConnector().get_portfolio_status(SCOPE)


def test_demo_portfolio_shape(portfolio):
    assert portfolio["found"] is True
    assert [p["project_id"] for p in portfolio["projects"]] == ["PROJ-14", "PROJ-22", "PROJ-31"]
    assert {p["project_id"]: p["status"] for p in portfolio["projects"]} == {
        "PROJ-14": "amber", "PROJ-22": "green", "PROJ-31": "red",
    }


@pytest.mark.parametrize(
    ("gate", "expected"),
    [
        ("G2-planning", {"PROJ-14": "pass", "PROJ-22": "pass", "PROJ-31": "conditional"}),
        ("G3-execution", {"PROJ-14": "fail", "PROJ-22": "pass", "PROJ-31": "fail"}),
    ],
)
def test_gate_decisions(portfolio, gate, expected):
    got = {p["project_id"]: evaluate_gate(p, gate)[0] for p in portfolio["projects"]}
    assert got == expected


def test_resource_allocation_utilization():
    from ma_pmo.agents.resource import ResourceAgent

    result = ResourceAgent().run({"task_ref": SCOPE})
    data = result["outputs"][0]["data"]
    assert data["utilization_pct"] == pytest.approx(45.1)
    assert data["overload_alerts"] == []
    assert callable(allocate)


def test_h3_rule_based_detection_is_perfect_on_fixtures():
    h3 = h3_risk_detection(SCOPE)
    assert (h3["precision"], h3["recall"], h3["f1"]) == (1.0, 1.0, 1.0)


@pytest.mark.parametrize(
    ("goal", "agents"),
    [
        ("Generate Q1 portfolio executive report", ["A5"]),
        ("Executive report including risks", ["A5", "A4"]),
        ("Compute critical path (CPM) schedule", ["A2"]),
        ("Optimize resource allocation", ["A3"]),
        ("Gate quality review", ["A6"]),
        ("Search similar cases and lessons learned", ["A7"]),
        ("리스크 포함 경영 보고", ["A5", "A4"]),
        ("hello", ["A5"]),
    ],
)
def test_keyword_routing_table(goal, agents):
    assert [d.agent for d in keyword_route(goal).delegations] == agents


def test_scenario_catalog_is_stable():
    assert len(SCENARIOS) == 20
    ids = [s["id"] for s in list_scenarios()]
    assert ids[:3] == ["knowledge_kickoff", "new_project_intake", "baseline_planning"]
    assert {s["category_id"] for s in list_scenarios()} == {
        "initiation", "execution", "governance", "closure", "portfolio",
    }
