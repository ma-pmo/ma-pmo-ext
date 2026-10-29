"""Resource allocation — the deterministic core of A3.

Skill-matching greedy allocation: fills each project's remaining effort week by week
against the weekly capacity of resources with the same skill. Computes
utilization/idle rate and overloads. No LLM required.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ma_pmo.core.i18n import tr

HORIZON_WEEKS = 12
_BASE_WEEK = 3  # allocate from 2026-W03


def _week_label(i: int) -> str:
    return f"2026-W{_BASE_WEEK + i:02d}"


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
    utilization_pct: float = 0.0
    idle_pct: float = 0.0


def _remaining_effort(project: dict) -> float:
    return sum(
        t.get("effort", 0.0) * (1.0 - t.get("percent_complete", 0.0) / 100.0)
        for t in project.get("tasks", [])
    )


def allocate(projects: list[dict], resources: list[dict]) -> AllocationResult:
    """Greedy allocation per skill. utilization = allocated hours / (capacity × weeks used)."""
    result = AllocationResult()

    # skill -> resources
    by_skill: dict[str, list[dict]] = {}
    for r in resources:
        by_skill.setdefault(r["skill"], []).append(r)

    # initialize remaining capacity per resource × week
    cap: dict[tuple[str, int], float] = {}
    for r in resources:
        for w in range(HORIZON_WEEKS):
            cap[(r["id"], w)] = r.get("capacity", 40.0)

    max_week_used = 0

    for proj in projects:
        skill = proj.get("skill", "")
        remaining = _remaining_effort(proj)
        res_pool = by_skill.get(skill, [])
        if remaining > 0 and not res_pool:
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
                    AllocLine(proj["project_id"], r["id"], _week_label(w), round(take, 1))
                )
                max_week_used = max(max_week_used, w + 1)
        if remaining > 0:  # cannot be absorbed within the horizon -> overload
            result.overload_alerts.append(
                tr(
                    f"{proj['project_id']}: '{skill}' capacity exceeded within "
                    f"{HORIZON_WEEKS} weeks ({remaining:.0f}h remaining)",
                    f"{proj['project_id']}: {HORIZON_WEEKS}주 내 '{skill}' 용량 초과 "
                    f"(잔여 {remaining:.0f}h)",
                )
            )

    allocated = sum(line.hours for line in result.lines)
    denom = sum(r.get("capacity", 40.0) for r in resources) * max(1, max_week_used)
    result.utilization_pct = round(allocated / denom * 100, 1) if denom else 0.0
    result.idle_pct = round(100.0 - result.utilization_pct, 1)
    return result
