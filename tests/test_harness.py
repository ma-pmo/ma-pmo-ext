"""Experiment harness — spec, run, aggregate, coverage, ablation, reports."""
from __future__ import annotations

from ma_pmo.harness import Experiment, render_markdown, run_experiment
from ma_pmo.harness.experiments import EXPERIMENTS
from ma_pmo.harness.reporters import render_csv, render_json


def test_experiment_builder():
    spec = (
        Experiment("t", "desc")
        .with_scenarios("quarterly_review")
        .repeat(2)
        .ablate("A4")
        .build()
    )
    assert spec.scenarios == ["quarterly_review"]
    assert spec.repeat == 2 and spec.ablate_agents == ["A4"]


def test_run_experiment_subset_with_repeats():
    spec = Experiment("t").with_scenarios("weekly_status", "quarterly_review").repeat(2)
    result = run_experiment(spec)
    assert len(result["runs"]) == 4  # 2 scenarios × 2 repetitions
    assert len(result["aggregate"]["per_scenario"]) == 2
    # coverage: H1 is covered by both scenarios
    assert "quarterly_review" in result["coverage"]["H1"]


def test_ablation_reports_finding_delta():
    spec = Experiment("t").with_scenarios("knowledge_kickoff").ablate("A7")
    result = run_experiment(spec)
    rows = result["ablation"]["A7"]
    assert rows, "scenarios with A7 must have ablation results"
    r = rows[0]
    # removing A7 must reduce outputs (knowledge output lost)
    assert r["ablated_outputs"] <= r["baseline_outputs"]


def test_reporters_render():
    result = run_experiment(Experiment("t").with_scenarios("weekly_status"))
    md = render_markdown(result)
    assert "Hypothesis coverage" in md and "Per-scenario summary" in md
    assert render_json(result).startswith("{")
    assert "scenario_id" in render_csv(result)


def test_registered_experiments_are_valid():
    assert set(EXPERIMENTS) >= {"full_suite", "hypothesis_matrix", "a7_ablation"}
    for s in EXPERIMENTS.values():
        assert s.build().name
