"""Roadmap 3: reading the mongodump, replaying fix versions to an as-of date, counting coverage."""
from __future__ import annotations

import gzip
import struct
import zipfile
from datetime import date, datetime

import pytest

bson = pytest.importorskip("bson")

from ma_pmo.benchmark import coverage  # noqa: E402
from ma_pmo.benchmark.dump import MAGIC, DumpError, iter_documents  # noqa: E402
from ma_pmo.benchmark.history import issue_history  # noqa: E402

END = struct.pack("<i", -1)
V1 = {"id": "1", "name": "1.0", "released": True, "releaseDate": "2020-03-01"}
V2 = {"id": "2", "name": "1.1", "released": True, "releaseDate": "2020-06-01"}
T = datetime(2020, 2, 16)  # 14 days before 1.0


def issue(key, *, fix=(), created="2020-01-01", resolved=None, changes=(), total=None,
          status="Open", moves=()):
    """A Jira issue; `changes` are (when, from_id, to_id) Fix Version edits, `moves` are
    (when, from_status, to_status) status changes."""
    histories = [{"created": f"{when}T00:00:00.000+0000",
                  "items": [{"field": "Fix Version", "from": f, "to": t}]}
                 for when, f, t in changes]
    histories += [{"created": f"{when}T00:00:00.000+0000",
                   "items": [{"field": "status", "fromString": a, "toString": b}]}
                  for when, a, b in moves]
    return {
        "key": key,
        "fields": {
            "project": {"key": "P"},
            "created": f"{created}T00:00:00.000+0000",
            "resolutiondate": f"{resolved}T00:00:00.000+0000" if resolved else None,
            "fixVersions": list(fix),
            "status": {"name": status},
            "versions": [],
        },
        "changelog": {"total": len(histories) if total is None else total, "histories": histories},
    }


def archive(blocks):
    """A gzipped mongodump archive: prelude, then (collection, docs) blocks."""
    names = sorted({c for c, _ in blocks})
    out = [MAGIC, bson.encode({"version": "0.1"})]
    out += [bson.encode({"db": "JiraReposAnon", "collection": c, "metadata": "{}", "size": 0,
                         "type": "collection"}) for c in names]
    out.append(END)
    for c, docs in blocks:
        out.append(bson.encode({"db": "JiraReposAnon", "collection": c, "EOF": False, "CRC": 0}))
        out += [bson.encode(d) for d in docs]
        out.append(END)
    return gzip.compress(b"".join(out))


def test_reads_interleaved_blocks_from_the_zip(tmp_path):
    path = tmp_path / "dump.zip"
    data = archive([("Apache", [issue("A-1")]), ("Jira", [issue("J-1")]),
                    ("Apache", [issue("A-2")])])
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("ThePublicJiraDataset/README.md", "x")
        z.writestr("ThePublicJiraDataset/3. DataDump/mongodump-JiraReposAnon.archive", data)
    assert [(c, d["key"]) for c, d in iter_documents(path)] == [
        ("Apache", "A-1"), ("Jira", "J-1"), ("Apache", "A-2")]


def test_a_truncated_dump_is_an_error_not_a_short_read(tmp_path):
    path = tmp_path / "dump.archive"
    path.write_bytes(archive([("Apache", [issue(f"A-{i}") for i in range(50)])])[:-200])
    with pytest.raises(DumpError):
        list(iter_documents(path))
    (tmp_path / "x.archive").write_bytes(gzip.compress(b"nope"))
    with pytest.raises(DumpError, match="not a mongodump"):
        list(iter_documents(tmp_path / "x.archive"))


def test_fix_versions_are_replayed_to_the_as_of_date():
    # added before T and still there; added after T; removed after T; removed before T
    kept = issue_history("C", issue("K", fix=[V1], changes=[("2020-01-10", None, "1")]))
    late = issue_history("C", issue("L", fix=[V1], changes=[("2020-02-20", None, "1")]))
    out = issue_history("C", issue("O", fix=[V2], changes=[("2020-01-10", None, "1"),
                                                          ("2020-02-28", "1", "2")]))
    gone = issue_history("C", issue("G", changes=[("2020-01-10", None, "1"),
                                                  ("2020-02-01", "1", None)]))
    assert [h.fix_versions_at(T) for h in (kept, late, out, gone)] == [{"1"}, set(), {"1"}, set()]
    # a fix version set at creation has no changelog entry and counts from the start
    assert issue_history("C", issue("N", fix=[V1])).scheduled("1", T)


def test_outcome_is_read_a_day_after_the_release():
    release = date(2020, 3, 1)
    cases = {
        "on_time": issue("A", fix=[V1], resolved="2020-03-01"),
        "late": issue("B", fix=[V1], resolved="2020-03-05"),  # kept V1, closed after release
        "moved_out": issue("D", fix=[V2], resolved="2020-05-01",
                           changes=[("2020-01-05", None, "1"), ("2020-02-28", "1", "2")]),
        "open": issue("O", fix=[V1]),  # never resolved
    }
    assert {o: issue_history("C", d).outcome("1", release) for o, d in cases.items()} == {
        o: o for o in cases}
    # out at release, put back afterwards: it still missed the release
    back = issue("K", fix=[V1], resolved="2020-04-01",
                 changes=[("2020-01-05", None, "1"), ("2020-02-29", "1", None),
                          ("2020-03-20", None, "1")])
    assert issue_history("C", back).outcome("1", release) == "moved_out"
    # resolved later after V was dropped: not late, slipped
    dropped = issue("X", fix=[V2], resolved="2020-05-01", changes=[("2020-01-05", None, "1"),
                                                                   ("2020-03-10", "1", "2")])
    assert issue_history("C", dropped).outcome("1", release) == "open"


def test_only_issues_open_at_the_as_of_date_are_scheduled():
    done_before = issue_history("C", issue("E", fix=[V1], resolved="2020-02-10"))
    created_after = issue_history("C", issue("F", fix=[V1], created="2020-02-20"))
    assert not done_before.scheduled("1", T)
    assert not created_after.scheduled("1", T)


def test_status_is_replayed_to_the_as_of_date():
    h = issue_history("C", issue("S", status="Resolved", moves=[
        ("2020-02-01", "Open", "In Progress"), ("2020-02-20", "In Progress", "Resolved")]))
    assert (h.status_at(datetime(2020, 1, 15)), h.status_at(T)) == ("open", "in progress")
    assert h.started(T) and not h.started(datetime(2020, 1, 15))
    assert not issue_history("C", issue("B", status="Backlog")).started(T)


def test_a_cut_off_changelog_is_flagged():
    cut = issue("A", changes=[("2020-01-01", None, "1")], total=5)
    assert not issue_history("C", cut).complete_log


def test_coverage_counts_usable_releases_per_collection(monkeypatch):
    monkeypatch.setattr(coverage, "MIN_RELEASES", 2)
    monkeypatch.setattr(coverage, "MIN_COLLECTIONS", 2)
    monkeypatch.setattr(coverage, "MIN_PER_COLLECTION", 1)
    cov = coverage.Coverage()
    for c in ("Apache", "Jira"):
        for i in range(3):  # 1 on time and started, 2 slipped: informative
            cov.add(c, issue(f"{c}-{i}", fix=[V1], resolved="2020-02-28" if i == 0 else None,
                             status="In Progress" if i == 0 else "Open"))
        cov.add(c, issue(f"{c}-late", fix=[V1], resolved="2020-03-20"))  # left out
    cov.add("Mojang", issue("M-1", fix=[V1]))  # too few issues
    report = cov.report(ks=[14], min_issues=3)
    r = report["k=14"]
    assert (r["usable_releases"], r["informative_releases"], r["go"]) == (2, 2, True)
    apache = r["per_collection"]["Apache"]
    assert (apache["issues"], apache["late_left_out"], apache["started_issues"]) == (3, 1, 1)
    assert apache["slip_rate"] == pytest.approx(0.667, abs=1e-3)
    assert apache["started_slip_rate"] == 0.0
    assert r["usable_started_releases"] == 0
    assert "Mojang" not in r["per_collection"]
    assert report["collections"]["Mojang"]["issues"] == 1
    assert "## As of 14 days before release: go" in coverage.to_markdown(report)
