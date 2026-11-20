"""ReplayTracker: a release as a tracker showed it at an as-of date T, and nothing after.

    tracker = ReplayTracker.load("bench-data")
    tracker.get_portfolio_status(portfolio_id(release, k=14))

It implements the tracker contract (`get_portfolio_status`), so the real agents run on it
unchanged. A portfolio is one release: `BENCH#<collection>/<version id>@<YYYY-MM-DD>`.

| project field | as of T |
|---|---|
| tasks | issues that existed at T with the release as a fix version at T, resolved ones included |
| task progress | 100 if resolved at T, 50 if started (status not a not-started one), else 0 |
| task effort | the original estimate at T in hours, else `DEFAULT_EFFORT` |
| task deps | issues of the same release that blocked it at T ("is blocked by", "depends on") |
| planned start | the earliest creation date among the tasks |
| planned finish, deadline | the release date |
| status colour | the trackers' rule (`integrations/mapping.py`) with today = T |

Tasks also carry their status, priority, assignee and type at T, for baselines. Every value
comes from `IssueHistory.snapshot(T)`; tests/test_benchmark_replay.py checks that changing
anything after T changes nothing.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from ma_pmo.benchmark.history import NOT_STARTED, IssueHistory, Release
from ma_pmo.benchmark.prepare import as_release, read_issues, read_releases
from ma_pmo.integrations.mapping import DEFAULT_EFFORT, IssueRecord, build_project

PREFIX = "BENCH#"


def portfolio_id(release: Release, k: int) -> str:
    t = release.release_date - timedelta(days=k)
    return f"{PREFIX}{release.collection}/{release.version_id}@{t.isoformat()}"


def parse_id(portfolio: str) -> tuple[str, str, date] | None:
    if not portfolio.startswith(PREFIX) or "@" not in portfolio or "/" not in portfolio:
        return None
    ref, _, day = portfolio[len(PREFIX):].rpartition("@")
    collection, _, version_id = ref.partition("/")
    try:
        return collection, version_id, date.fromisoformat(day)
    except ValueError:
        return None


def as_of(day: date) -> datetime:
    """T itself: the start of the as-of day, as the coverage counts and the outcomes use it."""
    return datetime.combine(day, datetime.min.time())


class ReplayTracker:
    def __init__(self, releases: list[Release], issues: list[IssueHistory]) -> None:
        self.releases = {(r.collection, r.version_id): r for r in releases}
        self.issues: dict[tuple[str, str], list[IssueHistory]] = defaultdict(list)
        for h in issues:
            for vid in h.version_ids():
                if (h.collection, vid) in self.releases:
                    self.issues[(h.collection, vid)].append(h)

    @classmethod
    def load(cls, data: str | Path) -> ReplayTracker:
        data = Path(data)
        return cls([as_release(r) for r in read_releases(data)], list(read_issues(data)))

    def get_portfolio_status(self, portfolio_id: str) -> dict:
        parsed = parse_id(portfolio_id)
        release = self.releases.get(parsed[:2]) if parsed else None
        if parsed is None or release is None:
            return {"portfolio_id": portfolio_id, "found": False, "projects": []}
        day = parsed[2]
        t = as_of(day)
        snaps = [s for h in self.issues[(release.collection, release.version_id)]
                 if (s := h.snapshot(t)) and release.version_id in s["fix_versions"]]
        keys = {s["key"] for s in snaps}
        records = [IssueRecord(
            key=s["key"],
            effort=s["estimate_hours"] or DEFAULT_EFFORT,
            progress=100.0 if s["resolved"] else 50.0 if s["status"] not in NOT_STARTED else 0.0,
            deps=[k for k in s["blocked_by"] if k in keys],
            created=s["created"],
        ) for s in sorted(snaps, key=lambda s: s["key"])]
        project = build_project(f"{release.project} {release.name}", records, today=day)
        extra = {s["key"]: s for s in snaps}
        for task in project["tasks"]:
            s = extra[task["task_id"]]
            task.update(status=s["status"], priority=s["priority"], assignee=s["assignee"],
                        type=s["type"])
        project.update(planned_finish=release.release_date.isoformat(),
                       deadline=release.release_date.isoformat())
        return {
            "portfolio_id": portfolio_id,
            "name": f"{release.collection} {release.project} {release.name}",
            "period": day.isoformat(),
            "plan_start": project["planned_start"],
            "as_of": day.isoformat(),
            "found": True,
            "projects": [project] if records else [],
        }

    def portfolios(self, k: int) -> list[str]:
        """Every release's portfolio id at offset `k`."""
        return [portfolio_id(r, k) for r in self.releases.values()]

    def outcomes(self, portfolio_id: str) -> dict[str, Any]:
        """What happened to the release's scheduled issues: for scoring only, never for agents."""
        parsed = parse_id(portfolio_id)
        release = self.releases.get(parsed[:2]) if parsed else None
        if parsed is None or release is None:
            return {}
        t = as_of(parsed[2])
        return {h.key: h.outcome(release.version_id, release.release_date)
                for h in self.issues[(release.collection, release.version_id)]
                if h.scheduled(release.version_id, t)}
