"""GitHub and Linear trackers: HTTP is mocked; the mapping rules are shared with Jira."""
from __future__ import annotations

import json

import httpx
import pytest

from ma_pmo.agents.planning import PlanningAgent
from ma_pmo.core.config import Settings
from ma_pmo.integrations import registry
from ma_pmo.integrations.github import GitHubTracker
from ma_pmo.integrations.linear import LinearTracker
from ma_pmo.integrations.mapping import blocked_by_in_text, effort_from_labels, skill_from_labels


def test_shared_label_and_text_rules():
    assert effort_from_labels(["bug", "hours: 12"]) == 12
    assert effort_from_labels(["points:3"]) == effort_from_labels(["sp:3"]) == 24
    assert effort_from_labels(["priority:high", "estimate:0"]) is None
    assert skill_from_labels(["Skill: data", "skill:backend"]) == "data"
    assert blocked_by_in_text("Blocked by #12 and depends on acme/web#3; see ENG-1. "
                              "Depends on: ENG-7") == ["#12", "acme/web#3", "ENG-7"]


GH_PAGE_1 = [
    {"number": 1, "state": "closed", "created_at": "2026-01-05T09:00:00Z",
     "labels": [{"name": "skill:backend"}, {"name": "points:2"}],
     "milestone": {"due_on": "2026-01-20T08:00:00Z"}, "body": ""},
    {"number": 2, "state": "open", "created_at": "2026-01-06T09:00:00Z",
     "labels": [{"name": "In Progress"}, {"name": "hours:24"}],
     "milestone": {"due_on": "2099-02-10T08:00:00Z"}, "body": "Blocked by #3"},
    {"number": 9, "state": "open", "pull_request": {"url": "..."}, "labels": []},
]
GH_PAGE_2 = [
    {"number": 3, "state": "open", "created_at": "2026-01-07T09:00:00Z", "labels": [],
     "milestone": None, "body": None},
    {"number": 4, "state": "closed", "state_reason": "not_planned",
     "created_at": "2026-01-01T00:00:00Z", "labels": []},
]


@pytest.mark.regression
def test_github_tracker_maps_issues():
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.url.params.get("page") == "2":
            return httpx.Response(200, json=GH_PAGE_2)
        nxt = '<https://api.github.com/repos/acme/api/issues?state=all&page=2>; rel="next"'
        return httpx.Response(200, json=GH_PAGE_1, headers={"Link": nxt})

    tracker = GitHubTracker(["acme/api"], "tok",
                            client=httpx.Client(transport=httpx.MockTransport(handler)))
    (project,) = tracker.get_portfolio_status("P")["projects"]

    assert len(calls) == 2 and calls[0].headers["authorization"] == "Bearer tok"
    assert calls[0].url.params["state"] == "all"
    assert project == {
        "project_id": "acme/api",
        "skill": "backend",
        "status": "amber",  # #2 is blocked by the open #3
        "planned_start": "2026-01-05",
        "planned_finish": "2099-02-10",
        "deadline": "2099-02-10",
        "percent_complete": round((16 * 100 + 24 * 50 + 8 * 0) / 48, 1),
        "tasks": [
            {"task_id": "acme/api#1", "wbs": "acme/api#1", "effort": 16.0, "deps": [],
             "percent_complete": 100.0},
            {"task_id": "acme/api#2", "wbs": "acme/api#2", "effort": 24.0,
             "deps": ["acme/api#3"], "percent_complete": 50.0},
            {"task_id": "acme/api#3", "wbs": "acme/api#3", "effort": 8.0, "deps": [],
             "percent_complete": 0.0},
        ],  # the pull request and the not-planned issue are left out
    }


def _linear_node(ident, state, *, estimate=None, due=None, labels=(), blocked_by=()):
    return {"identifier": ident, "estimate": estimate, "createdAt": "2026-02-01T10:00:00.000Z",
            "dueDate": due, "state": {"type": state},
            "labels": {"nodes": [{"name": n} for n in labels]},
            "inverseRelations": {"nodes": [{"type": "blocks", "issue": {"identifier": b}}
                                           for b in blocked_by]
                                 + [{"type": "related", "issue": {"identifier": "ENG-99"}}]}}


def test_linear_tracker_maps_issues():
    pages = [
        {"data": {"issues": {"nodes": [
            _linear_node("ENG-1", "completed", estimate=2, labels=["skill:data"]),
            _linear_node("ENG-2", "started", estimate=1, due="2025-01-31", blocked_by=["ENG-1"]),
        ], "pageInfo": {"hasNextPage": True, "endCursor": "c1"}}}},
        {"data": {"issues": {"nodes": [
            _linear_node("ENG-3", "unstarted", labels=["hours:4"]),
            _linear_node("ENG-4", "canceled"),
        ], "pageInfo": {"hasNextPage": False, "endCursor": None}}}},
    ]
    seen: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        seen.append(body["variables"])
        assert request.headers["authorization"] == "lin_api_key"
        return httpx.Response(200, json=pages[0 if body["variables"]["after"] is None else 1])

    tracker = LinearTracker(["ENG"], "lin_api_key",
                            client=httpx.Client(transport=httpx.MockTransport(handler)))
    (project,) = tracker.get_portfolio_status("P")["projects"]
    assert seen == [{"team": "ENG", "after": None}, {"team": "ENG", "after": "c1"}]
    tasks = {t["task_id"]: t for t in project["tasks"]}
    assert set(tasks) == {"ENG-1", "ENG-2", "ENG-3"}
    assert (tasks["ENG-1"]["effort"], tasks["ENG-2"]["effort"], tasks["ENG-3"]["effort"]) == (
        16.0, 8.0, 4.0)
    assert tasks["ENG-2"]["deps"] == ["ENG-1"] and tasks["ENG-2"]["percent_complete"] == 50.0
    assert project["status"] == "red"  # ENG-2 is open and past its due date
    assert project["skill"] == "data"


def test_linear_api_errors_surface():
    tracker = LinearTracker(["ENG"], "bad", client=httpx.Client(transport=httpx.MockTransport(
        lambda r: httpx.Response(200, json={"errors": [{"message": "Authentication required"}]}))))
    with pytest.raises(RuntimeError, match="Authentication required"):
        tracker.get_portfolio_status("P")


def test_registry_and_agents():
    names = {row["name"]: row for row in registry.status(Settings(
        _env_file=None, MA_PMO_INTEGRATIONS="github,linear", GITHUB_REPOS="acme/api"))}
    assert names["github"]["active"] and names["github"]["kind"] == "tracker"
    assert not names["linear"]["configured"]
    assert set(names["linear"]["missing_settings"]) == {"linear_api_key", "linear_team_keys"}

    tracker = GitHubTracker(["acme/api"], client=httpx.Client(transport=httpx.MockTransport(
        lambda r: httpx.Response(200, json=GH_PAGE_1[:2] + GH_PAGE_2[:1]))))
    (out,) = PlanningAgent(tracker=tracker).run({"task_ref": "P"})["outputs"]
    assert out["data"]["critical_path"] == ["acme/api#3", "acme/api#2"]
