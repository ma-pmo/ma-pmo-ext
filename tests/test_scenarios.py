"""Agent collaboration scenario engine — four-phase trace."""
from __future__ import annotations

import pytest

from ma_pmo.core.scenarios import SCENARIOS, list_scenarios, run_scenario

_PHASES = ["plan", "execute", "complete", "insight"]


def test_list_scenarios():
    items = list_scenarios()
    assert 15 <= len(items) <= 20, "15–20 organizational scenarios"
    assert {i["id"] for i in items} == set(SCENARIOS.keys())
    assert all(i["hypotheses"] and i["category"] and i["agents"] for i in items)


def test_all_scenarios_reference_valid_agents():
    valid = {"A2", "A3", "A4", "A5", "A6", "A7"}
    for sid, s in SCENARIOS.items():
        agents = {a for a, _ in s["steps"]}
        assert agents <= valid, f"{sid}: invalid agents {agents - valid}"
        assert all(h.startswith("H") for h in s["hypotheses"])


@pytest.mark.parametrize("sid", list(SCENARIOS.keys()))
def test_scenario_runs_four_phases(sid):
    trace = run_scenario(sid)
    phases = [p["phase"] for p in trace["phases"]]
    # includes plan -> (execute × N) -> complete -> insight in order
    assert phases[0] == "plan"
    assert phases[-2] == "complete"
    assert phases[-1] == "insight"
    assert "execute" in phases
    # number of execute phases = number of scenario steps
    n_exec = sum(1 for p in phases if p == "execute")
    assert n_exec == len(SCENARIOS[sid]["steps"])


def test_insight_maps_to_hypotheses():
    trace = run_scenario("quarterly_review")
    insight = trace["phases"][-1]
    assert insight["phase"] == "insight"
    assert insight["hypotheses"] == ["H1", "H3"]
    assert insight["findings"], "expected findings"
    assert all("hypothesis" in f for f in insight["findings"])


def test_execute_phase_records_timing():
    trace = run_scenario("risk_rebalance")
    execs = [p for p in trace["phases"] if p["phase"] == "execute"]
    assert all("elapsed_ms" in p for p in execs)
    assert all(p["results"] is not None for p in execs)


def test_scenario_captures_communications():
    # §4 structured messages exchanged during the run (audit log) are in the trace
    trace = run_scenario("quarterly_review")
    comms = trace["communications"]
    assert comms, "messages between agents must be captured"
    # check the worker -> A1 shape
    assert all("sender" in c and "receiver" in c and "schema" in c for c in comms)
    assert any(c["receiver"] == "A1" for c in comms)


def test_unknown_scenario_raises():
    with pytest.raises(KeyError):
        run_scenario("nope")
