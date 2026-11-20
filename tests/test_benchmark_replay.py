"""Roadmap 3, step 2: issue history at T, the prepared data, and a ReplayTracker that cannot see
past T (changing anything after T must change nothing it shows)."""
from __future__ import annotations

import dataclasses
import random
from datetime import date, datetime, timedelta

from ma_pmo.agents.planning import PlanningAgent
from ma_pmo.agents.risk import RiskAgent
from ma_pmo.benchmark import coverage, prepare
from ma_pmo.benchmark.history import FixChange, IssueHistory, issue_history
from ma_pmo.benchmark.replay import ReplayTracker, as_of, parse_id, portfolio_id

RELEASE = date(2020, 3, 1)
V1 = {"id": "1", "name": "1.0", "released": True, "releaseDate": RELEASE.isoformat()}
T = datetime(2020, 2, 16)  # 14 days before


def item(field, frm=None, to=None, frm_s=None, to_s=None):
    return {"field": field, "from": frm, "to": to, "fromString": frm_s, "toString": to_s}


def doc(key, *, created="2020-01-01", fix=(V1,), status="Open", resolution=None, history=(),
        links=(), estimate=None, priority="Major", assignee="u1", resolved_on=None):
    return {
        "key": key,
        "fields": {
            "project": {"key": "P"}, "created": f"{created}T00:00:00.000+0000",
            "resolutiondate": f"{resolved_on}T12:00:00.000+0000" if resolved_on else None,
            "fixVersions": list(fix), "versions": [],
            "status": {"name": status}, "resolution": {"name": resolution} if resolution else None,
            "priority": {"name": priority}, "assignee": {"key": assignee},
            "issuetype": {"name": "Bug"}, "timeoriginalestimate": estimate,
            "issuelinks": [{"type": {"inward": "is blocked by", "outward": "blocks"},
                            "inwardIssue": {"key": k}} for k in links],
        },
        "changelog": {"total": len(history), "histories": [
            {"created": f"{when}T12:00:00.000+0000", "items": items} for when, items in history]},
    }


def test_snapshot_replays_every_field_to_t():
    h = issue_history("C", doc(
        "A-1", status="Closed", resolution="Fixed", estimate=7200, priority="Blocker",
        assignee="u2", links=["A-2"], history=[
            ("2020-02-01", [item("status", frm_s="Open", to_s="In Progress"),
                            item("timeoriginalestimate", "3600", "7200")]),
            ("2020-02-20", [item("status", frm_s="In Progress", to_s="Closed"),
                            item("resolution", to_s="Fixed"),
                            item("priority", frm_s="Major", to_s="Blocker"),
                            item("assignee", frm="u1", to="u2"),
                            item("Link", to="A-2", to_s="This issue is blocked by A-2")]),
        ]))
    snap = h.snapshot(T)
    assert snap == {"key": "A-1", "created": "2020-01-01", "type": "bug",
                    "status": "in progress", "resolved": False, "priority": "major",
                    "assignee": "u1", "estimate_hours": 2.0, "fix_versions": ["1"],
                    "blocked_by": []}
    later = h.snapshot(datetime(2020, 2, 21))
    assert later["resolved"] and later["blocked_by"] == ["A-2"] and later["assignee"] == "u2"
    assert h.snapshot(datetime(2019, 12, 1)) is None  # not created yet


def test_records_round_trip():
    h = issue_history("C", doc("A-1", links=["A-2"], history=[
        ("2020-02-01", [item("Fix Version", None, "1"), item("status", frm_s="Open")])]))
    assert prepare.from_record(prepare.to_record(h)) == h


def _release_docs():
    return [
        doc("A-1", status="In Progress",
            history=[("2020-01-10", [item("Fix Version", None, "1")])]),
        doc("A-2", links=["A-1"]),  # blocked by A-1, not started
        doc("A-3", status="Closed", resolution="Fixed", resolved_on="2020-02-10",
            history=[("2020-02-10", [item("resolution", to_s="Fixed")])]),  # done before T
        doc("A-4", created="2020-02-20"),  # created after T
    ]


def _tracker(docs=None, tmp_path=None):
    cov = coverage.Coverage()
    for d in docs or _release_docs():
        cov.add("C", d)
    if tmp_path is None:
        release = cov.releases[("C", "1")]
        return ReplayTracker([release], [h for hs in cov.issues.values() for h in hs]), release
    prepare.prepare(cov, tmp_path, ks=[14], min_issues=1)
    tracker = ReplayTracker.load(tmp_path)
    return tracker, tracker.releases[("C", "1")]


def test_the_tracker_shows_the_release_at_t(tmp_path):
    tracker, release = _tracker(tmp_path=tmp_path)
    pid = portfolio_id(release, 14)
    assert pid == "BENCH#C/1@2020-02-16" and parse_id(pid) == ("C", "1", date(2020, 2, 16))
    status = tracker.get_portfolio_status(pid)
    [project] = status["projects"]
    tasks = {t["task_id"]: t for t in project["tasks"]}
    assert set(tasks) == {"A-1", "A-2", "A-3"}  # A-4 did not exist yet
    assert [tasks[k]["percent_complete"] for k in ("A-1", "A-2", "A-3")] == [50.0, 0.0, 100.0]
    assert tasks["A-2"]["deps"] == ["A-1"] and project["status"] == "amber"  # blocked, open
    assert project["deadline"] == "2020-03-01" and project["planned_start"] == "2020-01-01"
    assert tasks["A-1"]["effort"] == 8.0 and tasks["A-1"]["priority"] == "major"
    assert tracker.get_portfolio_status("BENCH#C/9@2020-02-16")["found"] is False
    assert tracker.get_portfolio_status("PORTFOLIO#2026-Q1")["found"] is False
    assert tracker.outcomes(pid) == {"A-1": "open", "A-2": "open"}


def _after_t(h: IssueHistory, rnd: random.Random) -> IssueHistory:
    """`h` with random changes after T, current values updated to match."""
    later = [as_of(T.date()) + timedelta(days=rnd.randint(1, 30), hours=rnd.randint(0, 23))
             for _ in range(6)]
    later.sort()
    new_vid = rnd.choice(["1", "2"])
    adds = new_vid not in h.fix_versions
    return dataclasses.replace(
        h,
        status="closed", status_changes=(*h.status_changes, (later[0], h.status)),
        resolution="fixed", resolution_changes=(*h.resolution_changes, (later[1], h.resolution)),
        resolved=later[1],
        priority="blocker", priority_changes=(*h.priority_changes, (later[2], h.priority)),
        assignee="someone-else", assignee_changes=(*h.assignee_changes, (later[3], h.assignee)),
        estimate="99999", estimate_changes=(*h.estimate_changes, (later[4], h.estimate)),
        blockers=h.blockers | {"A-3"},
        blocker_changes=(*h.blocker_changes, (later[5], "A-3", True)) if "A-3" not in h.blockers
        else h.blocker_changes,
        fix_versions=(h.fix_versions | {new_vid}) if adds else (h.fix_versions - {new_vid}),
        changes=(*h.changes, FixChange(later[5], new_vid, added=adds)),
    )


def test_nothing_after_t_changes_what_the_tracker_shows():
    tracker, release = _tracker()
    pid = portfolio_id(release, 14)
    before = tracker.get_portfolio_status(pid)
    rnd = random.Random(7)
    for _ in range(20):
        issues = [h for hs in tracker.issues.values() for h in hs]
        changed = ReplayTracker([release], [_after_t(h, rnd) for h in issues])
        assert changed.get_portfolio_status(pid) == before


def test_real_agents_run_on_the_replay():
    tracker, release = _tracker()
    pid = portfolio_id(release, 14)
    plan = PlanningAgent(tracker).run({"task_ref": pid})
    assert plan["outputs"][0]["data"]["critical_path"]
    risks = RiskAgent(tracker).run({"task_ref": pid})
    assert {o["schema"] for o in risks["outputs"]} <= {"risk_alert.v1"}
