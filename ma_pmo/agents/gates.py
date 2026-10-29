"""Governance gate evaluation — the deterministic core of A6.

Checks project facts (schedule, WBS, dependencies, SPI, progress) against gate criteria.
No LLM required. Each criterion is critical or not: a critical failure -> fail,
a non-critical failure -> conditional.
"""
from __future__ import annotations

from dataclasses import dataclass

from ma_pmo.agents.cpm import compute_cpm
from ma_pmo.agents.risk_signals import compute_signals
from ma_pmo.core.i18n import tr

# Supported stage gates
GATES = ["G1-initiation", "G2-planning", "G3-execution", "G4-closure"]

# Legacy Korean gate IDs (v0.0.x) -> current IDs
_GATE_ALIASES = {
    "G1-착수": "G1-initiation",
    "G2-계획완료": "G2-planning",
    "G3-실행중간": "G3-execution",
    "G4-종료": "G4-closure",
}


def normalize_gate(gate: str) -> str:
    """Accept current IDs, legacy Korean IDs, or a bare prefix such as "G2"."""
    if gate in GATES:
        return gate
    if gate in _GATE_ALIASES:
        return _GATE_ALIASES[gate]
    prefix = gate.split("-")[0].upper()
    for g in GATES:
        if g.startswith(prefix + "-"):
            return g
    return gate


@dataclass
class Criterion:
    name: str
    passed: bool
    critical: bool
    note: str = ""


def _spi(project: dict) -> float | None:
    tasks = project.get("tasks", [])
    pv = sum(t.get("effort", 0.0) for t in tasks)
    if pv <= 0:
        return None
    ev = sum(t.get("effort", 0.0) * (t.get("percent_complete", 0.0) / 100.0) for t in tasks)
    return round(ev / pv, 3)


def _has_cycle(tasks: list[dict]) -> bool:
    order = compute_cpm(tasks)
    # compute_cpm appends remaining nodes on cycles, so detect via the topological
    # invariant: a predecessor placed after its successor means a cycle.
    pos = {t.task_id: i for i, t in enumerate(order.tasks)}
    for t in order.tasks:
        for d in t.deps:
            if d in pos and pos[d] > pos[t.task_id]:
                return True
    return False


def _criteria(project: dict, gate: str) -> list[Criterion]:
    tasks = project.get("tasks", [])
    gate = normalize_gate(gate)
    if gate == "G1-initiation":
        return [
            Criterion(
                tr("Start date set", "착수일 설정"), bool(project.get("planned_start")), True
            ),
            Criterion(tr("Deadline set", "마감일 설정"), bool(project.get("deadline")), True),
            Criterion(tr("Tasks defined", "태스크 정의됨"), len(tasks) > 0, True),
        ]
    if gate == "G2-planning":
        all_wbs = all(t.get("wbs") for t in tasks) and bool(tasks)
        slack = None
        pf, dl = project.get("planned_finish"), project.get("deadline")
        if pf and dl:
            from datetime import datetime

            try:
                slack = (
                    datetime.strptime(dl, "%Y-%m-%d").date()
                    - datetime.strptime(pf, "%Y-%m-%d").date()
                ).days
            except ValueError:
                slack = None
        return [
            Criterion(tr("WBS assigned to all tasks", "모든 태스크 WBS 부여"), all_wbs, True),
            Criterion(
                tr("No dependency cycles (DAG)", "의존성 순환 없음(DAG)"),
                not _has_cycle(tasks),
                True,
            ),
            Criterion(
                tr("Critical path computable", "임계경로 산출 가능"), len(tasks) > 0, True
            ),
            Criterion(
                tr("Schedule slack ≥ 0", "일정 여유 ≥ 0"),
                slack is not None and slack >= 0,
                False,
                note=(
                    tr(f"slack {slack}d", f"여유 {slack}일")
                    if slack is not None
                    else tr("not computed", "미산정")
                ),
            ),
        ]
    if gate == "G3-execution":
        spi = _spi(project)
        sig = compute_signals(project)
        return [
            Criterion(
                "SPI ≥ 0.8", spi is not None and spi >= 0.8, True, note=f"SPI={spi}"
            ),
            Criterion(
                tr("No blocked tasks", "차단 태스크 없음"),
                not sig.blocked_tasks,
                False,
                note=(
                    tr(f"blocked {sig.blocked_tasks}", f"차단 {sig.blocked_tasks}")
                    if sig.blocked_tasks
                    else ""
                ),
            ),
        ]
    if gate == "G4-closure":
        return [
            Criterion(
                tr("Overall progress 100%", "전체 진척 100%"),
                project.get("percent_complete", 0.0) >= 100.0,
                True,
                note=f"{project.get('percent_complete', 0.0)}%",
            )
        ]
    raise ValueError(f"unknown gate: {gate}")


def evaluate_gate(project: dict, gate: str) -> tuple[str, list[Criterion], list[str]]:
    """Gate review -> (decision, checklist, conditions)."""
    criteria = _criteria(project, gate)
    critical_fail = [c for c in criteria if c.critical and not c.passed]
    minor_fail = [c for c in criteria if not c.critical and not c.passed]

    if critical_fail:
        decision = "fail"
    elif minor_fail:
        decision = "conditional"
    else:
        decision = "pass"

    conditions = [
        tr(f"{c.name} required ({c.note})", f"{c.name} 충족 필요 ({c.note})").strip()
        for c in minor_fail
    ]
    return decision, criteria, conditions
