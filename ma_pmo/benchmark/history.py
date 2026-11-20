"""An issue's fix-version history, replayed to an as-of date.

Jira keeps an issue's current fix versions and a changelog of "Fix Version" changes (each adds
or removes one version id). The fix versions an issue had at time T are the current ones with
every change after T undone. Version ids are unique within one Jira instance (a collection),
not across them.

An issue is **scheduled** for release V at T when it existed at T, was unresolved at T, and had V
as a fix version at T. Its **outcome** is read one day after the release date (D):

| outcome | at D | label |
|---|---|---|
| `on_time` | resolved, V a fix version | not slipped |
| `moved_out` | V no longer a fix version | slipped |
| `open` | V a fix version, unresolved, and never resolved in V afterwards | slipped |
| `late` | V a fix version, unresolved, resolved later with V kept | left out |

`late` is left out of the label: such issues are often closed after the release by QA or clean-up
(in Jira's own tracker half of them within a week), so "did it make the release" is unclear.

The status at T says whether work had **started**: any status other than a not-started one
(`NOT_STARTED`); the subset of started issues leaves out backlog that only carried a version.

The other fields a replay needs are kept the same way, as the current value plus the value before
each change: status, resolution, priority, assignee, original estimate, and the issues that block
this one ("is blocked by" / "depends on" links). `snapshot(t)` gives all of them as of T and
nothing later, which is what the ReplayTracker shows agents (`replay.py`).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

FIX_FIELDS = {"fix version", "fix version/s", "fixversions"}
BLOCKING = ("is blocked by", "depends on")  # link texts naming an issue this one waits for
GRACE = timedelta(days=1)
NOT_STARTED = {"open", "new", "to do", "backlog", "reopened", "needs triage", "triage", "untriaged",
               "submitted", "awaiting triage", "pending triage", "unconfirmed", "created"}
SLIPPED = {"moved_out", "open"}


def parse_time(value: str | None) -> datetime | None:
    """Jira's `2022-01-03T14:50:04.000+0000` as a naive UTC datetime (seconds kept)."""
    return datetime.fromisoformat(value[:19]) if value else None


@dataclass(frozen=True)
class Release:
    collection: str
    version_id: str
    project: str
    name: str
    release_date: date


@dataclass(frozen=True)
class FixChange:
    at: datetime
    version_id: str
    added: bool


@dataclass(frozen=True, slots=True)  # millions are kept in memory
class IssueHistory:
    collection: str
    key: str
    created: datetime
    resolved: datetime | None
    fix_versions: frozenset[str]
    changes: tuple[FixChange, ...]  # oldest first
    complete_log: bool  # the changelog was not cut off
    status: str = ""  # current status name, lower case
    status_changes: tuple[tuple[datetime, str], ...] = ()  # (when, status before), oldest first
    # the same shape for the fields a replay shows: current value, (when, value before) changes
    resolution: str = ""
    resolution_changes: tuple[tuple[datetime, str], ...] = ()
    priority: str = ""
    priority_changes: tuple[tuple[datetime, str], ...] = ()
    assignee: str = ""
    assignee_changes: tuple[tuple[datetime, str], ...] = ()
    estimate: str = ""  # original estimate in seconds, "" when none
    estimate_changes: tuple[tuple[datetime, str], ...] = ()
    blockers: frozenset[str] = frozenset()  # keys of the issues blocking this one now
    blocker_changes: tuple[tuple[datetime, str, bool], ...] = ()  # (when, key, added)
    issuetype: str = ""

    def fix_versions_at(self, t: datetime) -> set[str]:
        versions = set(self.fix_versions)
        for c in reversed(self.changes):
            if c.at <= t:
                break
            if c.added:
                versions.discard(c.version_id)
            else:
                versions.add(c.version_id)
        return versions

    def scheduled(self, version_id: str, t: datetime) -> bool:
        if self.created > t or (self.resolved is not None and self.resolved <= t):
            return False
        return version_id in self.fix_versions_at(t)

    def outcome(self, version_id: str, release_date: date) -> str:
        """`on_time`, `moved_out`, `open` or `late` (see the module docstring)."""
        due = datetime.combine(release_date, datetime.min.time()) + GRACE
        if version_id not in self.fix_versions_at(due):
            return "moved_out"
        if self.resolved is not None and self.resolved <= due:
            return "on_time"
        if self.resolved is not None and version_id in self.fix_versions:
            return "late"
        return "open"

    def status_at(self, t: datetime) -> str:
        for at, before in self.status_changes:
            if at > t:
                return before
        return self.status

    def started(self, t: datetime) -> bool:
        return self.status_at(t) not in NOT_STARTED

    def blockers_at(self, t: datetime) -> set[str]:
        keys = set(self.blockers)
        for at, key, added in reversed(self.blocker_changes):
            if at <= t:
                break
            if added:
                keys.discard(key)
            else:
                keys.add(key)
        return keys

    def snapshot(self, t: datetime) -> dict[str, Any] | None:
        """What a tracker showed about the issue at T, or None if it did not exist yet."""
        if self.created > t:
            return None
        estimate = _at(self.estimate_changes, self.estimate, t)
        return {
            "key": self.key, "created": self.created.date().isoformat(),
            "type": self.issuetype, "status": self.status_at(t),
            "resolved": bool(_at(self.resolution_changes, self.resolution, t)),
            "priority": _at(self.priority_changes, self.priority, t),
            "assignee": _at(self.assignee_changes, self.assignee, t),
            "estimate_hours": round(int(estimate) / 3600, 2) if estimate.isdigit() else None,
            "fix_versions": sorted(self.fix_versions_at(t)),
            "blocked_by": sorted(self.blockers_at(t)),
        }

    def version_ids(self) -> set[str]:
        """Every version the issue had as a fix version at some point."""
        return set(self.fix_versions) | {c.version_id for c in self.changes}


def _at(changes: tuple[tuple[datetime, str], ...], current: str, t: datetime) -> str:
    """The value at T: the value before the first change after T, else the current one."""
    for at, before in changes:
        if at > t:
            return before
    return current


def releases_in(collection: str, doc: dict[str, Any]) -> list[Release]:
    """Released versions with a release date that the issue names as a fix or affected version."""
    fields = doc.get("fields") or {}
    project = (fields.get("project") or {}).get("key", "")
    out = []
    for v in (fields.get("fixVersions") or []) + (fields.get("versions") or []):
        if v.get("id") and v.get("released") and v.get("releaseDate"):
            out.append(Release(collection, v["id"], project, v.get("name", ""),
                               date.fromisoformat(v["releaseDate"][:10])))
    return out


def issue_history(collection: str, doc: dict[str, Any]) -> IssueHistory | None:
    """The issue's fix-version history, or None for an issue without a creation date."""
    fields = doc.get("fields") or {}
    created = parse_time(fields.get("created"))
    if created is None:
        return None
    log = doc.get("changelog") or {}
    histories = log.get("histories") or []
    changes = []
    statuses = []
    tracked: dict[str, list[tuple[datetime, str]]] = {
        "resolution": [], "priority": [], "assignee": [], "timeoriginalestimate": []}
    blocker_changes = []
    for h in histories:
        at = parse_time(h.get("created"))
        if at is None:
            continue
        for item in h.get("items") or []:
            name = (item.get("field") or "").lower()
            if name == "status":
                statuses.append((at, (item.get("fromString") or "").lower()))
            elif name in tracked:
                before = item.get("from") if name in ("assignee", "timeoriginalestimate") \
                    else item.get("fromString")
                tracked[name].append((at, (before or "").lower() if name != "assignee"
                                      else before or ""))
            elif name == "link":
                for side, added in (("to", True), ("from", False)):
                    text = (item.get(f"{side}String") or "").lower()
                    if item.get(side) and any(b in text for b in BLOCKING):
                        blocker_changes.append((at, item[side], added))
            if name not in FIX_FIELDS:
                continue
            if item.get("from"):
                changes.append(FixChange(at, item["from"], added=False))
            if item.get("to"):
                changes.append(FixChange(at, item["to"], added=True))
    changes.sort(key=lambda c: c.at)  # stable: a removal and an addition at once keep their order
    statuses.sort(key=lambda s: s[0])
    for values in tracked.values():
        values.sort(key=lambda s: s[0])
    blocker_changes.sort(key=lambda s: s[0])
    blockers = frozenset(
        (link.get("inwardIssue") or {}).get("key", "")
        for link in fields.get("issuelinks") or []
        if link.get("inwardIssue")
        and any(b in ((link.get("type") or {}).get("inward") or "").lower() for b in BLOCKING))
    return IssueHistory(
        collection=collection,
        key=doc.get("key", ""),
        created=created,
        resolved=parse_time(fields.get("resolutiondate")),
        fix_versions=frozenset(v["id"] for v in fields.get("fixVersions") or [] if v.get("id")),
        changes=tuple(changes),
        complete_log=len(histories) >= (log.get("total") or 0),
        status=((fields.get("status") or {}).get("name") or "").lower(),
        status_changes=tuple(statuses),
        resolution=((fields.get("resolution") or {}).get("name") or "").lower(),
        resolution_changes=tuple(tracked["resolution"]),
        priority=((fields.get("priority") or {}).get("name") or "").lower(),
        priority_changes=tuple(tracked["priority"]),
        assignee=(fields.get("assignee") or {}).get("key") or "",
        assignee_changes=tuple(tracked["assignee"]),
        estimate=str(fields.get("timeoriginalestimate") or ""),
        estimate_changes=tuple(tracked["timeoriginalestimate"]),
        blockers=blockers - {""},
        blocker_changes=tuple(blocker_changes),
        issuetype=((fields.get("issuetype") or {}).get("name") or "").lower(),
    )
