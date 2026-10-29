"""A4 risk signal analyzer — deterministic (rule-based).

Computes risk signals observable in issue-tracker status. It needs no LLM, so it also
serves as the "rule-based baseline" for paper H3 (precision/recall vs. the LLM agent).

Signals:
- schedule_slack_days   : days of slack from planned_finish to deadline (negative = at risk)
- completion_gap_pct    : share of remaining work (100 - percent complete)
- stalled_tasks         : tasks with low progress although predecessors are done (stalled burndown)
- blocked_tasks         : tasks that cannot proceed because predecessors are unfinished
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime

_STALL_THRESHOLD = 50.0  # "stalled" if progress (%) is below this while dependencies are done


def _parse(d: str | None) -> date | None:
    if not d:
        return None
    try:
        return datetime.strptime(d, "%Y-%m-%d").date()
    except ValueError:
        return None


@dataclass
class ProjectSignals:
    project_id: str
    status: str  # green|amber|red (as reported by the tracker)
    percent_complete: float
    schedule_slack_days: int | None
    completion_gap_pct: float
    stalled_tasks: list[str] = field(default_factory=list)
    blocked_tasks: list[str] = field(default_factory=list)

    @property
    def has_signal(self) -> bool:
        """Whether any signal is worth treating as a risk."""
        return (
            self.status in {"amber", "red"}
            or (self.schedule_slack_days is not None and self.schedule_slack_days < 0)
            or bool(self.stalled_tasks)
            or bool(self.blocked_tasks)
        )

    def as_dict(self) -> dict:
        return asdict(self)


def compute_signals(project: dict) -> ProjectSignals:
    """Single project status dict -> signals."""
    tasks = project.get("tasks", [])
    done = {t["task_id"] for t in tasks if t.get("percent_complete", 0) >= 100}

    stalled, blocked = [], []
    for t in tasks:
        pct = t.get("percent_complete", 0)
        deps = t.get("deps", [])
        deps_done = all(d in done for d in deps)
        if pct >= 100:
            continue
        if deps_done and pct < _STALL_THRESHOLD:
            stalled.append(t["task_id"])
        elif not deps_done:
            blocked.append(t["task_id"])

    pf, dl = _parse(project.get("planned_finish")), _parse(project.get("deadline"))
    slack = (dl - pf).days if pf and dl else None

    return ProjectSignals(
        project_id=project["project_id"],
        status=project.get("status", "green"),
        percent_complete=project.get("percent_complete", 0.0),
        schedule_slack_days=slack,
        completion_gap_pct=round(100.0 - project.get("percent_complete", 0.0), 1),
        stalled_tasks=stalled,
        blocked_tasks=blocked,
    )


def baseline_severity(sig: ProjectSignals) -> str:
    """Rule-based severity (H3 comparison group); the baseline checked against the LLM."""
    if sig.status == "red" or (
        sig.schedule_slack_days is not None and sig.schedule_slack_days < 0
    ):
        return "high"
    if sig.status == "amber" or sig.stalled_tasks or sig.blocked_tasks:
        return "medium"
    return "low"


def analyze_portfolio(status: dict) -> list[ProjectSignals]:
    """Portfolio status -> projects that have signals."""
    return [
        sig
        for p in status.get("projects", [])
        if (sig := compute_signals(p)).has_signal
    ]
