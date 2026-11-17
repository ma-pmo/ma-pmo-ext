"""An issue's fix-version history, replayed to an as-of date.

Jira keeps an issue's current fix versions and a changelog of "Fix Version" changes (each adds
or removes one version id). The fix versions an issue had at time T are the current ones with
every change after T undone. Version ids are unique within one Jira instance (a collection),
not across them.

An issue is **scheduled** for release V at T when it existed at T, was unresolved at T, and had V
as a fix version at T. It **slipped** when V is no longer one of its fix versions, or it was not
resolved by the release date plus one day.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

FIX_FIELDS = {"fix version", "fix version/s", "fixversions"}
GRACE = timedelta(days=1)


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

    def slipped(self, version_id: str, release_date: date) -> bool:
        if version_id not in self.fix_versions:
            return True
        due = datetime.combine(release_date, datetime.min.time()) + GRACE
        return self.resolved is None or self.resolved > due

    def version_ids(self) -> set[str]:
        """Every version the issue had as a fix version at some point."""
        return set(self.fix_versions) | {c.version_id for c in self.changes}


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
    for h in histories:
        at = parse_time(h.get("created"))
        if at is None:
            continue
        for item in h.get("items") or []:
            if (item.get("field") or "").lower() not in FIX_FIELDS:
                continue
            if item.get("from"):
                changes.append(FixChange(at, item["from"], added=False))
            if item.get("to"):
                changes.append(FixChange(at, item["to"], added=True))
    changes.sort(key=lambda c: c.at)  # stable: a removal and an addition at once keep their order
    return IssueHistory(
        collection=collection,
        key=doc.get("key", ""),
        created=created,
        resolved=parse_time(fields.get("resolutiondate")),
        fix_versions=frozenset(v["id"] for v in fields.get("fixVersions") or [] if v.get("id")),
        changes=tuple(changes),
        complete_log=len(histories) >= (log.get("total") or 0),
    )
