"""Critical Path Method (CPM) — the deterministic core of A2 planning.

Runs forward/backward passes over WBS, dependencies and effort to compute each task's
early/late start and finish, slack, and the critical path. No LLM (paper §5: CPM/OR-Tools).

Assumption: effort is in hours, converted to duration_days at 8h/day per person.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta

HOURS_PER_DAY = 8.0


def _duration_days(effort_hours: float) -> int:
    return max(1, math.ceil(effort_hours / HOURS_PER_DAY))


@dataclass
class CpmTask:
    task_id: str
    wbs: str
    duration: int  # days
    deps: list[str]
    early_start: int = 0  # days relative to project start
    early_finish: int = 0
    late_start: int = 0
    late_finish: int = 0

    @property
    def slack(self) -> int:
        return self.late_start - self.early_start

    @property
    def is_critical(self) -> bool:
        return self.slack == 0


@dataclass
class CpmResult:
    tasks: list[CpmTask]
    project_duration: int  # days
    critical_path: list[str]

    def projected_finish(self, start: str | None) -> str | None:
        """Projected finish (calendar date) from planned_start (ISO)."""
        if not start:
            return None
        try:
            d0 = datetime.strptime(start, "%Y-%m-%d").date()
        except ValueError:
            return None
        return (d0 + timedelta(days=self.project_duration)).isoformat()

    @staticmethod
    def offset_date(start: str | None, days: int) -> str:
        if not start:
            return f"+{days}d"
        try:
            d0 = datetime.strptime(start, "%Y-%m-%d").date()
        except ValueError:
            return f"+{days}d"
        return (d0 + timedelta(days=days)).isoformat()


def _topo_order(tasks: dict[str, CpmTask]) -> list[str]:
    """Kahn topological sort; on cycles, remaining nodes are appended to avoid looping."""
    indeg = {tid: 0 for tid in tasks}
    for t in tasks.values():
        for d in t.deps:
            if d in tasks:
                indeg[t.task_id] += 1
    queue = [tid for tid, n in indeg.items() if n == 0]
    order: list[str] = []
    while queue:
        tid = queue.pop(0)
        order.append(tid)
        for other in tasks.values():
            if tid in other.deps and other.task_id in indeg:
                indeg[other.task_id] -= 1
                if indeg[other.task_id] == 0:
                    queue.append(other.task_id)
    if len(order) < len(tasks):  # cycle guard
        order += [tid for tid in tasks if tid not in order]
    return order


def compute_cpm(raw_tasks: list[dict]) -> CpmResult:
    """Task dicts -> CPM result."""
    tasks: dict[str, CpmTask] = {
        t["task_id"]: CpmTask(
            task_id=t["task_id"],
            wbs=t.get("wbs", ""),
            duration=_duration_days(t.get("effort", 0.0)),
            deps=[d for d in t.get("deps", [])],
        )
        for t in raw_tasks
    }
    if not tasks:
        return CpmResult(tasks=[], project_duration=0, critical_path=[])

    order = _topo_order(tasks)

    # forward pass: ES/EF
    for tid in order:
        t = tasks[tid]
        t.early_start = max(
            (tasks[d].early_finish for d in t.deps if d in tasks), default=0
        )
        t.early_finish = t.early_start + t.duration

    project_duration = max(t.early_finish for t in tasks.values())

    # backward pass: LF/LS
    for tid in reversed(order):
        t = tasks[tid]
        successors = [o for o in tasks.values() if tid in o.deps]
        t.late_finish = (
            min((s.late_start for s in successors), default=project_duration)
        )
        t.late_start = t.late_finish - t.duration

    critical = sorted(
        (t for t in tasks.values() if t.is_critical), key=lambda x: x.early_start
    )
    return CpmResult(
        tasks=[tasks[tid] for tid in order],
        project_duration=project_duration,
        critical_path=[t.task_id for t in critical],
    )
