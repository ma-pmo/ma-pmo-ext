"""A4 deterministic signal analyzer (rule-based baseline, H3)."""
from __future__ import annotations

from ma_pmo.agents.risk_signals import baseline_severity, compute_signals


def _project(**kw):
    base = {
        "project_id": "PROJ-X",
        "status": "green",
        "percent_complete": 90.0,
        "planned_finish": "2026-03-27",
        "deadline": "2026-03-31",
        "tasks": [],
    }
    base.update(kw)
    return base


def test_red_status_is_high_severity():
    sig = compute_signals(_project(status="red", percent_complete=25.0))
    assert sig.has_signal
    assert baseline_severity(sig) == "high"


def test_negative_schedule_slack_is_high():
    # planned_finish after deadline -> negative slack -> high
    sig = compute_signals(
        _project(status="green", planned_finish="2026-04-10", deadline="2026-04-03")
    )
    assert sig.schedule_slack_days is not None and sig.schedule_slack_days < 0
    assert baseline_severity(sig) == "high"


def test_stalled_task_detection():
    # predecessor done (T1 = 100%) but T2 stuck at 10% -> stalled, medium
    proj = _project(
        status="green",
        percent_complete=55.0,
        tasks=[
            {"task_id": "T1", "deps": [], "percent_complete": 100},
            {"task_id": "T2", "deps": ["T1"], "percent_complete": 10},
        ],
    )
    sig = compute_signals(proj)
    assert "T2" in sig.stalled_tasks
    assert baseline_severity(sig) == "medium"


def test_blocked_task_detection():
    # predecessor (T1) unfinished -> T2 is blocked
    proj = _project(
        tasks=[
            {"task_id": "T1", "deps": [], "percent_complete": 40},
            {"task_id": "T2", "deps": ["T1"], "percent_complete": 0},
        ],
    )
    sig = compute_signals(proj)
    assert "T2" in sig.blocked_tasks


def test_healthy_project_no_signal():
    sig = compute_signals(_project(status="green", percent_complete=95.0))
    assert not sig.has_signal
    assert baseline_severity(sig) == "low"
