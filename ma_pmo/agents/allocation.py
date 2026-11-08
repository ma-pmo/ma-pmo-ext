"""Resource allocation — the deterministic core of A3.

Skill-matching greedy allocation: fills each project's remaining effort week by week
against the weekly capacity of resources with the same skill. Computes
utilization/idle rate and overloads. No LLM required.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, timedelta

from ma_pmo.connectors.calendar import week_days
from ma_pmo.core.i18n import tr

HORIZON_WEEKS = 12


def _week_labels(start: str | None) -> list[str]:
    """ISO week labels of the horizon, from `start` or else the current week."""
    today = date.today()
    monday = week_days(start)[0] if start else today - timedelta(days=today.weekday())
    weeks = (monday + timedelta(weeks=i) for i in range(HORIZON_WEEKS))
    return ["{}-W{:02d}".format(*week.isocalendar()[:2]) for week in weeks]


@dataclass
class AllocLine:
    project_id: str
    resource_id: str
    week: str
    hours: float


@dataclass
class AllocationResult:
    lines: list[AllocLine] = field(default_factory=list)
    overload_alerts: list[str] = field(default_factory=list)
    unstaffed: list[dict] = field(default_factory=list)  # project_id, skill, hours, reason
    utilization_pct: float = 0.0
    idle_pct: float = 0.0


def _remaining_effort(project: dict) -> float:
    return sum(
        t.get("effort", 0.0) * (1.0 - t.get("percent_complete", 0.0) / 100.0)
        for t in project.get("tasks", [])
    )


def allocate(projects: list[dict], resources: list[dict],
             busy: Callable[[str, str], float] | None = None,
             start: str | None = None) -> AllocationResult:
    """Greedy allocation per skill. utilization = allocated hours / available hours in the weeks
    used. `busy(resource_id, week)` (a calendar) takes hours off a person's weekly capacity.
    `start` is the first ISO week of the horizon; the default is the current week."""
    result = AllocationResult()
    labels = _week_labels(start)

    # skill -> resources
    by_skill: dict[str, list[dict]] = {}
    for r in resources:
        by_skill.setdefault(r["skill"], []).append(r)

    # initialize remaining capacity per resource × week
    cap: dict[tuple[str, int], float] = {}
    for r in resources:
        for w in range(HORIZON_WEEKS):
            blocked = busy(r["id"], labels[w]) if busy else 0.0
            cap[(r["id"], w)] = max(0.0, r.get("capacity", 40.0) - blocked)
    available = dict(cap)  # before allocation, for the utilization denominator

    max_week_used = 0

    for proj in projects:
        skill = proj.get("skill", "")
        remaining = _remaining_effort(proj)
        res_pool = by_skill.get(skill, [])
        if remaining > 0 and not res_pool:
            result.unstaffed.append({"project_id": proj["project_id"], "skill": skill,
                                     "remaining_hours": round(remaining, 1),
                                     "reason": "no_skill"})
            result.overload_alerts.append(
                tr(
                    f"{proj['project_id']}: no resource with skill '{skill}' "
                    f"({remaining:.0f}h remaining)",
                    f"{proj['project_id']}: '{skill}' 스킬 자원 없음 (잔여 {remaining:.0f}h)",
                )
            )
            continue

        # fill week by week, then resource by resource
        for w in range(HORIZON_WEEKS):
            if remaining <= 0:
                break
            for r in res_pool:
                if remaining <= 0:
                    break
                avail = cap[(r["id"], w)]
                if avail <= 0:
                    continue
                take = min(avail, remaining)
                cap[(r["id"], w)] -= take
                remaining -= take
                result.lines.append(
                    AllocLine(proj["project_id"], r["id"], labels[w], round(take, 1))
                )
                max_week_used = max(max_week_used, w + 1)
        if remaining > 0:  # cannot be absorbed within the horizon -> overload
            result.unstaffed.append({"project_id": proj["project_id"], "skill": skill,
                                     "remaining_hours": round(remaining, 1),
                                     "reason": "capacity"})
            result.overload_alerts.append(
                tr(
                    f"{proj['project_id']}: '{skill}' capacity exceeded within "
                    f"{HORIZON_WEEKS} weeks ({remaining:.0f}h remaining)",
                    f"{proj['project_id']}: {HORIZON_WEEKS}주 내 '{skill}' 용량 초과 "
                    f"(잔여 {remaining:.0f}h)",
                )
            )

    allocated = sum(line.hours for line in result.lines)
    weeks = range(max(1, max_week_used))
    denom = sum(available[(r["id"], w)] for r in resources for w in weeks)
    result.utilization_pct = round(allocated / denom * 100, 1) if denom else 0.0
    result.idle_pct = round(100.0 - result.utilization_pct, 1)
    return result
