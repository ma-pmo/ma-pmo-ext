"""Shared mapping from tracker issues to the project shape agents read.

Every tracker (Jira, GitHub, Linear, …) turns its issues into `IssueRecord`s and calls
`build_project`, so the same rules apply everywhere:

| MA-PMO              | rule                                                              |
|---------------------|-------------------------------------------------------------------|
| progress (%)        | effort-weighted average of the tasks                              |
| planned start       | earliest issue creation date                                      |
| planned finish      | latest due date of unfinished issues (else latest due date)       |
| deadline            | latest due date                                                   |
| status colour       | red: overdue open issue · amber: blocked by an open task · green  |
| skill               | first skill hint found on the issues, else "general"              |
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

HOURS_PER_POINT = 8.0
DEFAULT_EFFORT = 8.0

# "blocked by #12", "depends on owner/repo#12", "Blocked by: ENG-4"
_BLOCKED_BY = re.compile(
    r"(?:blocked by|depends on)[:\s]+((?:[\w.-]+/[\w.-]+)?#\d+|[A-Z][A-Z0-9]+-\d+)", re.IGNORECASE
)


@dataclass
class IssueRecord:
    key: str
    effort: float
    progress: float
    deps: list[str] = field(default_factory=list)
    created: str | None = None  # YYYY-MM-DD
    due: str | None = None  # YYYY-MM-DD
    skill: str | None = None


def effort_from_labels(labels: list[str]) -> float | None:
    """`hours:12` → 12 h; `points:3`, `sp:3` or `estimate:3` → 3 × 8 h; else None."""
    for label in labels:
        name, _, value = label.lower().replace(" ", "").partition(":")
        try:
            number = float(value)
        except ValueError:
            continue
        if number <= 0:
            continue
        if name in ("hours", "h"):
            return number
        if name in ("points", "sp", "estimate"):
            return number * HOURS_PER_POINT
    return None


def skill_from_labels(labels: list[str]) -> str | None:
    """`skill:backend` → "backend"."""
    for label in labels:
        name, _, value = label.partition(":")
        if name.strip().lower() == "skill" and value.strip():
            return value.strip()
    return None


def blocked_by_in_text(text: str | None) -> list[str]:
    """Issue references after "blocked by" / "depends on" in a description."""
    return [m.group(1) for m in _BLOCKED_BY.finditer(text or "")]


def build_project(project_id: str, records: list[IssueRecord]) -> dict:
    today = date.today().isoformat()
    tasks = [
        {"task_id": r.key, "wbs": r.key, "effort": r.effort, "deps": r.deps,
         "percent_complete": r.progress}
        for r in records
    ]
    created = [r.created for r in records if r.created]
    due_all = [r.due for r in records if r.due]
    due_open = [r.due for r in records if r.due and r.progress < 100]
    overdue = any(d < today for d in due_open)
    done_ids = {r.key for r in records if r.progress >= 100}
    blocked = any(r.progress < 100 and any(d not in done_ids for d in r.deps) for r in records)
    total = sum(r.effort for r in records) or 1.0
    earned = sum(r.effort * r.progress / 100 for r in records)
    skills = [r.skill for r in records if r.skill]
    return {
        "project_id": project_id,
        "skill": skills[0] if skills else "general",
        "status": "red" if overdue else "amber" if blocked else "green",
        "planned_start": min(created) if created else None,
        "planned_finish": max(due_open) if due_open else (max(due_all) if due_all else None),
        "deadline": max(due_all) if due_all else None,
        "percent_complete": round(earned / total * 100, 1),
        "tasks": tasks,
    }
