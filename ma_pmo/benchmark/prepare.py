"""`ma-pmo benchmark prepare <dump> --out DIR`: keep the releases the benchmark uses and the
history of their issues, so later steps read a few MB instead of the 5.8 GB dump.

Writes to DIR:

| file | content |
|---|---|
| `releases.jsonl` | one usable release per line, with the labelled issues at T per offset k |
| `issues.jsonl.gz` | full history of every issue that was ever a fix-version issue of one |
| `manifest.json` | dump file size, offsets, minimum issues, counts, and the MA-PMO version |

Outcomes are not written: they are read from the same histories when the benchmark is scored,
and the ReplayTracker shows agents only what was known at T (`replay.py`).
"""
from __future__ import annotations

import gzip
import json
from collections.abc import Iterable, Iterator
from datetime import date, datetime
from pathlib import Path
from typing import Any

from ma_pmo import __version__
from ma_pmo.benchmark.coverage import MIN_ISSUES, Coverage, ReleaseRow
from ma_pmo.benchmark.history import FixChange, IssueHistory, Release

_TIMES = ("status_changes", "resolution_changes", "priority_changes", "assignee_changes",
          "estimate_changes")


def to_record(h: IssueHistory) -> dict[str, Any]:
    """An issue history as JSON-ready data (times as ISO strings)."""
    record: dict[str, Any] = {
        "collection": h.collection, "key": h.key, "created": h.created.isoformat(),
        "resolved": h.resolved.isoformat() if h.resolved else None,
        "fix_versions": sorted(h.fix_versions),
        "changes": [[c.at.isoformat(), c.version_id, c.added] for c in h.changes],
        "complete_log": h.complete_log, "status": h.status, "resolution": h.resolution,
        "priority": h.priority, "assignee": h.assignee, "estimate": h.estimate,
        "blockers": sorted(h.blockers), "issuetype": h.issuetype,
        "blocker_changes": [[at.isoformat(), key, added] for at, key, added in h.blocker_changes],
    }
    for name in _TIMES:
        record[name] = [[at.isoformat(), before] for at, before in getattr(h, name)]
    return record


def from_record(r: dict[str, Any]) -> IssueHistory:
    t = datetime.fromisoformat
    return IssueHistory(
        collection=r["collection"], key=r["key"], created=t(r["created"]),
        resolved=t(r["resolved"]) if r["resolved"] else None,
        fix_versions=frozenset(r["fix_versions"]),
        changes=tuple(FixChange(t(at), vid, added) for at, vid, added in r["changes"]),
        complete_log=r["complete_log"], status=r["status"], resolution=r["resolution"],
        priority=r["priority"], assignee=r["assignee"], estimate=r["estimate"],
        blockers=frozenset(r["blockers"]), issuetype=r["issuetype"],
        blocker_changes=tuple((t(at), key, added) for at, key, added in r["blocker_changes"]),
        **{name: tuple((t(at), before) for at, before in r[name]) for name in _TIMES},
    )


def release_record(release: Release, rows: dict[int, ReleaseRow]) -> dict[str, Any]:
    return {"collection": release.collection, "version_id": release.version_id,
            "project": release.project, "name": release.name,
            "release_date": release.release_date.isoformat(),
            "scheduled": {str(k): ReleaseRow.labelled(r.outcomes) for k, r in rows.items()}}


def as_release(r: dict[str, Any]) -> Release:
    return Release(r["collection"], r["version_id"], r["project"], r["name"],
                   date.fromisoformat(r["release_date"]))


def prepare(cov: Coverage, out: Path, ks: Iterable[int] = (14, 28),
            min_issues: int = MIN_ISSUES, source: dict[str, Any] | None = None) -> dict[str, Any]:
    """Write the usable releases of `cov` and their issues' histories to `out`."""
    ks = list(ks)
    by_release: dict[tuple[str, str], dict[int, ReleaseRow]] = {}
    for k in ks:
        for row in cov.rows(k):
            if ReleaseRow.labelled(row.outcomes) >= min_issues:
                key = (row.release.collection, row.release.version_id)
                by_release.setdefault(key, {})[k] = row
    out.mkdir(parents=True, exist_ok=True)
    keep: dict[tuple[str, str], IssueHistory] = {}
    with open(out / "releases.jsonl", "w", encoding="utf-8") as f:
        for key, rows in sorted(by_release.items()):
            f.write(json.dumps(release_record(cov.releases[key], rows)) + "\n")
            for h in cov.issues.get(key, []):
                keep[(h.collection, h.key)] = h
    with gzip.open(out / "issues.jsonl.gz", "wt", encoding="utf-8") as f:
        for _, h in sorted(keep.items()):
            f.write(json.dumps(to_record(h)) + "\n")
    manifest = {"ma_pmo": __version__, "as_of_days": ks, "min_issues": min_issues,
                "releases": len(by_release), "issues": len(keep), "source": source or {}}
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    return manifest


def read_releases(data: Path) -> Iterator[dict[str, Any]]:
    with open(data / "releases.jsonl", encoding="utf-8") as f:
        for line in f:
            yield json.loads(line)


def read_issues(data: Path) -> Iterator[IssueHistory]:
    with gzip.open(data / "issues.jsonl.gz", "rt", encoding="utf-8") as f:
        for line in f:
            yield from_record(json.loads(line))
