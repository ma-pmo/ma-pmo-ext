"""Is there enough history to benchmark on? Counts usable releases per collection.

    ma-pmo benchmark coverage <dump> [--k 14 28] [--min-issues 20]

A release is usable at as-of offset k when at least `min_issues` issues were scheduled for it k
days before its release date (`history`). The bar set in roadmap 3 is at least 200 usable
releases, with at least 10 in each of at least 3 collections. Releases where between 10% and 90%
of the scheduled issues slipped are counted separately: in the others every issue (or none)
slipped, so there is little to tell apart.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from ma_pmo.benchmark.history import IssueHistory, Release, issue_history, releases_in

MIN_ISSUES = 20
MIN_RELEASES = 200
MIN_COLLECTIONS = 3
MIN_PER_COLLECTION = 10
INFORMATIVE = (0.1, 0.9)


@dataclass(frozen=True)
class ReleaseRow:
    release: Release
    k: int
    scheduled: int
    slipped: int
    moved_out: int  # slipped by losing the fix version (others: resolved late or never)

    @property
    def slip_rate(self) -> float:
        return self.slipped / self.scheduled if self.scheduled else 0.0


class Coverage:
    """Collects releases and issue histories document by document, then counts."""

    def __init__(self) -> None:
        self.releases: dict[tuple[str, str], Release] = {}
        self.issues: dict[tuple[str, str], list[IssueHistory]] = defaultdict(list)
        self.counts: dict[str, Counter[str]] = defaultdict(Counter)

    def add(self, collection: str, doc: dict[str, Any]) -> None:
        c = self.counts[collection]
        c["issues"] += 1
        for r in releases_in(collection, doc):
            self.releases.setdefault((collection, r.version_id), r)
        h = issue_history(collection, doc)
        if h is None:
            return
        c["complete_log"] += h.complete_log
        c["with_fix_version"] += bool(h.fix_versions)
        c["with_fix_changes"] += bool(h.changes)
        for vid in h.version_ids():
            self.issues[(collection, vid)].append(h)

    def rows(self, k: int) -> list[ReleaseRow]:
        out = []
        for ref, release in self.releases.items():
            t = datetime.combine(release.release_date, datetime.min.time()) - timedelta(days=k)
            scheduled = slipped = moved = 0
            for h in self.issues.get(ref, []):
                if not h.scheduled(release.version_id, t):
                    continue
                scheduled += 1
                if h.slipped(release.version_id, release.release_date):
                    slipped += 1
                    moved += release.version_id not in h.fix_versions
            if scheduled:
                out.append(ReleaseRow(release, k, scheduled, slipped, moved))
        return out

    def report(self, ks: Iterable[int] = (14, 28), min_issues: int = MIN_ISSUES) -> dict[str, Any]:
        counts = {c: dict(v) for c, v in sorted(self.counts.items())}
        result: dict[str, Any] = {"collections": counts}
        for k in ks:
            usable = [r for r in self.rows(k) if r.scheduled >= min_issues]
            per: dict[str, list[ReleaseRow]] = defaultdict(list)
            for r in usable:
                per[r.release.collection].append(r)
            lo, hi = INFORMATIVE
            enough = [c for c, rs in per.items() if len(rs) >= MIN_PER_COLLECTION]
            result[f"k={k}"] = {
                "usable_releases": len(usable),
                "informative_releases": sum(lo <= r.slip_rate <= hi for r in usable),
                "collections_with_enough": len(enough),
                "go": len(usable) >= MIN_RELEASES and len(enough) >= MIN_COLLECTIONS,
                "per_collection": {
                    c: {
                        "releases": len(rs),
                        "informative": sum(lo <= r.slip_rate <= hi for r in rs),
                        "issues": sum(r.scheduled for r in rs),
                        "slip_rate": _rate(rs, "slipped"),
                        "moved_out_rate": _rate(rs, "moved_out"),
                        "years": f"{min(r.release.release_date.year for r in rs)}–"
                                 f"{max(r.release.release_date.year for r in rs)}",
                    }
                    for c, rs in sorted(per.items(), key=lambda kv: -len(kv[1]))
                },
            }
        return result


def _rate(rows: list[ReleaseRow], field: str) -> float:
    return round(sum(getattr(r, field) for r in rows) / sum(r.scheduled for r in rows), 3)


def scan(path: str | Path, *, progress: bool = False) -> Coverage:
    from ma_pmo.benchmark.dump import iter_documents

    cov = Coverage()
    for i, (collection, doc) in enumerate(iter_documents(path), 1):
        cov.add(collection, doc)
        if progress and i % 100_000 == 0:
            print(f"… {i:,} issues", flush=True)
    return cov


def to_markdown(report: dict[str, Any]) -> str:
    lines = ["# Benchmark coverage", ""]
    for key, r in report.items():
        if not key.startswith("k="):
            continue
        verdict = "go" if r["go"] else "no-go"
        lines += [
            f"## As of {key[2:]} days before release: {verdict}",
            "",
            f"{r['usable_releases']} usable releases ({r['informative_releases']} informative), "
            f"{r['collections_with_enough']} collections with at least {MIN_PER_COLLECTION}. "
            f"Bar: {MIN_RELEASES} releases, {MIN_COLLECTIONS} collections.",
            "",
            "| collection | releases | informative | issues | slipped | moved out | years |",
            "|---|---|---|---|---|---|---|",
        ]
        for c, v in r["per_collection"].items():
            lines.append(f"| {c} | {v['releases']} | {v['informative']} | {v['issues']} | "
                         f"{v['slip_rate']:.0%} | {v['moved_out_rate']:.0%} | {v['years']} |")
        lines.append("")
    return "\n".join(lines)
