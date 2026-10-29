"""A6 gate evaluation logic (deterministic)."""
from __future__ import annotations

from ma_pmo.agents.gates import evaluate_gate


def _project(**kw):
    base = {
        "project_id": "P",
        "planned_start": "2026-01-06",
        "planned_finish": "2026-03-27",
        "deadline": "2026-03-31",
        "percent_complete": 60.0,
        "tasks": [
            {"task_id": "T1", "wbs": "1.1", "effort": 40, "deps": [], "percent_complete": 100},
            {"task_id": "T2", "wbs": "1.2", "effort": 40, "deps": ["T1"], "percent_complete": 50},
        ],
    }
    base.update(kw)
    return base


def test_g1_pass_when_dates_and_tasks_set():
    decision, criteria, _ = evaluate_gate(_project(), "G1-initiation")
    assert decision == "pass"
    assert all(c.passed for c in criteria)


def test_g2_fail_when_wbs_missing():
    proj = _project(
        tasks=[{"task_id": "T1", "wbs": "", "effort": 40, "deps": [], "percent_complete": 0}]
    )
    decision, _, _ = evaluate_gate(proj, "G2-planning")
    assert decision == "fail"  # missing WBS = critical


def test_g2_conditional_when_schedule_slack_negative():
    # slack < 0 is non-critical -> conditional
    proj = _project(planned_finish="2026-04-10", deadline="2026-04-03")
    decision, _, conditions = evaluate_gate(proj, "G2-planning")
    assert decision == "conditional"
    assert conditions


def test_g2_detects_dependency_cycle():
    proj = _project(
        tasks=[
            {"task_id": "T1", "wbs": "1", "effort": 8, "deps": ["T2"], "percent_complete": 0},
            {"task_id": "T2", "wbs": "2", "effort": 8, "deps": ["T1"], "percent_complete": 0},
        ]
    )
    decision, criteria, _ = evaluate_gate(proj, "G2-planning")
    dag = next(c for c in criteria if "DAG" in c.name)
    assert not dag.passed and decision == "fail"


def test_g3_fail_low_spi():
    proj = _project(
        tasks=[{"task_id": "T1", "wbs": "1", "effort": 100, "deps": [], "percent_complete": 10}]
    )
    decision, _, _ = evaluate_gate(proj, "G3-execution")
    assert decision == "fail"  # SPI=0.1 < 0.8


def test_g4_pass_only_when_complete():
    assert evaluate_gate(_project(percent_complete=100.0), "G4-closure")[0] == "pass"
    assert evaluate_gate(_project(percent_complete=80.0), "G4-closure")[0] == "fail"
