"""A2 CPM algorithm — critical path correctness."""
from __future__ import annotations

from ma_pmo.agents.cpm import compute_cpm


def test_linear_chain_all_critical():
    # T1->T2->T3, 8h (= 1 day) each. All on the critical path.
    tasks = [
        {"task_id": "T1", "wbs": "1", "effort": 8, "deps": []},
        {"task_id": "T2", "wbs": "2", "effort": 8, "deps": ["T1"]},
        {"task_id": "T3", "wbs": "3", "effort": 8, "deps": ["T2"]},
    ]
    r = compute_cpm(tasks)
    assert r.project_duration == 3
    assert r.critical_path == ["T1", "T2", "T3"]


def test_parallel_branch_longer_is_critical():
    # T1 -> (T2: 3 days | T3: 1 day) -> T4. Critical path is T1-T2-T4.
    tasks = [
        {"task_id": "T1", "wbs": "1", "effort": 8, "deps": []},        # 1 day
        {"task_id": "T2", "wbs": "2", "effort": 24, "deps": ["T1"]},   # 3 days
        {"task_id": "T3", "wbs": "3", "effort": 8, "deps": ["T1"]},    # 1 day
        {"task_id": "T4", "wbs": "4", "effort": 8, "deps": ["T2", "T3"]},  # 1 day
    ]
    r = compute_cpm(tasks)
    assert r.project_duration == 5  # 1+3+1
    assert r.critical_path == ["T1", "T2", "T4"]
    # the short branch T3 has slack, so it is not critical
    t3 = next(t for t in r.tasks if t.task_id == "T3")
    assert t3.slack == 2


def test_projected_finish_date():
    tasks = [{"task_id": "T1", "wbs": "1", "effort": 16, "deps": []}]  # 2 days
    r = compute_cpm(tasks)
    assert r.projected_finish("2026-01-06") == "2026-01-08"


def test_empty():
    r = compute_cpm([])
    assert r.project_duration == 0 and r.critical_path == []
