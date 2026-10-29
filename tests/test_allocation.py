"""A3 resource allocation algorithm."""
from __future__ import annotations

from ma_pmo.agents.allocation import allocate


def test_skill_matched_allocation():
    projects = [
        {
            "project_id": "P1",
            "skill": "backend",
            "tasks": [{"task_id": "t", "effort": 40, "percent_complete": 0}],
        }
    ]
    resources = [{"id": "R1", "skill": "backend", "capacity": 40}]
    r = allocate(projects, resources)
    assert sum(ln.hours for ln in r.lines) == 40
    assert all(ln.resource_id == "R1" for ln in r.lines)
    assert not r.overload_alerts


def test_missing_skill_raises_overload():
    projects = [
        {
            "project_id": "P1",
            "skill": "ml",
            "tasks": [{"task_id": "t", "effort": 40, "percent_complete": 0}],
        }
    ]
    resources = [{"id": "R1", "skill": "backend", "capacity": 40}]
    r = allocate(projects, resources)
    assert r.overload_alerts and "ml" in r.overload_alerts[0]
    assert not r.lines


def test_remaining_effort_excludes_completed():
    # 50% done -> 20h remaining
    projects = [
        {
            "project_id": "P1",
            "skill": "backend",
            "tasks": [{"task_id": "t", "effort": 40, "percent_complete": 50}],
        }
    ]
    resources = [{"id": "R1", "skill": "backend", "capacity": 40}]
    r = allocate(projects, resources)
    assert sum(ln.hours for ln in r.lines) == 20
    assert 0 < r.utilization_pct <= 100
    assert round(r.utilization_pct + r.idle_pct, 1) == 100.0
