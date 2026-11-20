"""Issue features at T, for the benchmark's baselines: only what was known at T.

The features follow the issue-delay literature (Choetkiertikul et al., ASE 2015 / EMSE 2017):
the issue's state and history so far, its links, and the load on its assignee.

| feature | at T |
|---|---|
| `started`, `in_review` | status is not a not-started one; status mentions review/resolved |
| `priority` | 0 (trivial) … 4 (blocker); 2 when unknown |
| `bug`, `feature`, `task` | issue type |
| `age_days` | days since creation |
| `days_left` | days from T to the release date (the as-of offset k) |
| `since_status_days` | days since the last status change (or creation) |
| `status_changes`, `reschedules` | status changes so far; times a fix version was removed so far |
| `blocked_by_open` | issues of the release blocking it and still unresolved at T |
| `blocks` | issues of the release it blocks at T |
| `has_assignee`, `assignee_load` | an assignee; that assignee's open issues in the release |
| `has_estimate` | an original estimate |
| `release_open`, `release_open_share` | open scheduled issues in the release, and their share |
"""
from __future__ import annotations

from collections import Counter
from datetime import date, datetime

from ma_pmo.benchmark.history import NOT_STARTED, IssueHistory

PRIORITY = {"trivial": 0, "lowest": 0, "minor": 1, "low": 1, "major": 2, "medium": 2,
            "normal": 2, "critical": 3, "high": 3, "blocker": 4, "highest": 4, "urgent": 4}
NAMES = ("started", "in_review", "priority", "bug", "feature", "task", "age_days", "days_left",
         "since_status_days", "status_changes", "reschedules", "blocked_by_open", "blocks",
         "has_assignee", "assignee_load", "has_estimate", "release_open", "release_open_share")


def _last_status_change(h: IssueHistory, t: datetime) -> datetime:
    before = [at for at, _ in h.status_changes if at <= t]
    return max(before) if before else h.created


def release_features(issues: list[IssueHistory], version_id: str, release_date: date,
                     t: datetime) -> dict[str, dict[str, float]]:
    """Features of every issue scheduled for the release at T, by issue key."""
    snaps = {h.key: (h, s) for h in issues
             if (s := h.snapshot(t)) and version_id in s["fix_versions"]}
    open_keys = {k for k, (_, s) in snaps.items() if not s["resolved"]}
    scheduled = {h.key: h for h in issues if h.scheduled(version_id, t)}
    load = Counter(snaps[k][1]["assignee"] for k in open_keys if snaps[k][1]["assignee"])
    blocks = Counter(b for k in open_keys for b in snaps[k][1]["blocked_by"] if b in snaps)
    out = {}
    for key, h in scheduled.items():
        s = snaps.get(key, (h, h.snapshot(t)))[1]
        if s is None:
            continue
        status = s["status"]
        out[key] = {
            "started": float(status not in NOT_STARTED),
            "in_review": float(any(w in status for w in ("review", "resolved", "verif"))),
            "priority": float(PRIORITY.get(s["priority"], 2)),
            "bug": float("bug" in s["type"]),
            "feature": float(any(w in s["type"] for w in ("feature", "improvement", "story"))),
            "task": float("task" in s["type"]),
            "age_days": float((t - h.created).days),
            "days_left": float((release_date - t.date()).days),
            "since_status_days": float((t - _last_status_change(h, t)).days),
            "status_changes": float(sum(at <= t for at, _ in h.status_changes)),
            "reschedules": float(sum(c.at <= t and not c.added for c in h.changes)),
            "blocked_by_open": float(sum(b in open_keys for b in s["blocked_by"])),
            "blocks": float(blocks.get(key, 0)),
            "has_assignee": float(bool(s["assignee"])),
            "assignee_load": float(load.get(s["assignee"], 0)) if s["assignee"] else 0.0,
            "has_estimate": float(s["estimate_hours"] is not None),
            "release_open": float(len(open_keys)),
            "release_open_share": len(open_keys) / len(snaps) if snaps else 0.0,
        }
    return out
