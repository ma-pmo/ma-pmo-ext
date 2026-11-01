"""Integration hub: registry, notifiers (Slack/webhook), Jira tracker, dispatch isolation."""
from __future__ import annotations

import json

import httpx
import pytest

from ma_pmo.connectors.jira_mock import MockJiraConnector
from ma_pmo.core.config import Settings
from ma_pmo.core.i18n import use_lang
from ma_pmo.core.schemas.message import AgentMessage, Intent, MessagePayload
from ma_pmo.integrations import dispatch, registry
from ma_pmo.integrations.base import Event, EventType, IntegrationSpec
from ma_pmo.integrations.events import approval_resolved_event, events_from_message
from ma_pmo.integrations.jira import JiraTracker
from ma_pmo.integrations.notifiers import SlackNotifier, WebhookNotifier


def _settings(**env: str) -> Settings:
    return Settings(_env_file=None, **env)  # type: ignore[call-arg]


class Recorder:
    """Fake notifier that records what it receives."""

    def __init__(self, name: str = "recorder", fail: bool = False) -> None:
        self.name = name
        self.fail = fail
        self.events: list[Event] = []

    def send(self, event: Event) -> None:
        if self.fail:
            raise RuntimeError("boom")
        self.events.append(event)


def _capture_client(store: list[httpx.Request], status: int = 200) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        store.append(request)
        return httpx.Response(status, text="ok")

    return httpx.Client(transport=httpx.MockTransport(handler))


def _message(schema: str, data: dict, *, confidence: float = 0.9,
             gated: bool = False) -> AgentMessage:
    return AgentMessage(
        sender="A4", receiver="A1", intent=Intent.PROPOSE, task_ref="PORTFOLIO#2026-Q1/PROJ-31",
        payload=MessagePayload(schema_=schema, data=data), confidence=confidence,
        human_gate_required=gated,
    )


# ── registry ─────────────────────────────────────────────────────
@pytest.mark.smoke
def test_builtins_are_registered():
    names = set(registry.available())
    assert {"slack", "webhook", "jira"} <= names


@pytest.mark.regression
def test_status_reports_missing_settings_without_secrets():
    s = _settings(MA_PMO_INTEGRATIONS="slack,jira,nope",
                  SLACK_WEBHOOK_URL="https://hooks.slack.test/T/B/secret")
    rows = {r["name"]: r for r in registry.status(s)}
    assert rows["slack"]["active"] is True
    assert rows["jira"]["enabled"] and not rows["jira"]["configured"]
    assert "jira_api_token" in rows["jira"]["missing_settings"]
    assert rows["webhook"]["enabled"] is False
    assert rows["nope"]["kind"] == "unknown"
    assert "secret" not in json.dumps(rows)


@pytest.mark.regression
def test_tracker_falls_back_to_demo_data_until_jira_is_configured():
    assert isinstance(registry.get_tracker(_settings()), MockJiraConnector)
    half = _settings(MA_PMO_INTEGRATIONS="jira", JIRA_BASE_URL="https://x.atlassian.net")
    assert isinstance(registry.get_tracker(half), MockJiraConnector)
    full = _settings(MA_PMO_INTEGRATIONS="jira", JIRA_BASE_URL="https://x.atlassian.net",
                     JIRA_EMAIL="a@b.c", JIRA_API_TOKEN="t", JIRA_PROJECT_KEYS="PAY, DATA")
    tracker = registry.get_tracker(full)
    assert isinstance(tracker, JiraTracker) and tracker.project_keys == ["PAY", "DATA"]


def test_plugin_entry_points_are_loaded(monkeypatch):
    spec = IntegrationSpec(name="teams", kind="notifier", description="plugin",
                           required_settings=(), factory=lambda s: Recorder("teams"))

    class EP:
        name = "teams"

        def load(self):
            return spec

    class BrokenEP:
        name = "broken"

        def load(self):
            raise ImportError("missing dependency")

    monkeypatch.setattr(registry, "entry_points", lambda group: [EP(), BrokenEP()])
    assert registry.available()["teams"] is spec
    notifiers = registry.build_notifiers(_settings(MA_PMO_INTEGRATIONS="teams"))
    assert [n.name for n in notifiers] == ["teams"]


# ── events ───────────────────────────────────────────────────────
@pytest.mark.regression
@pytest.mark.parametrize(
    ("schema", "data", "gated", "expected"),
    [
        ("risk_alert.v1", {"project_id": "PROJ-31", "severity": "high", "signal": "s",
                           "mitigation": "m", "rationale": "r"}, True,
         ["risk.detected", "approval.requested"]),
        ("risk_alert.v1", {"project_id": "PROJ-14", "severity": "medium", "signal": "s",
                           "mitigation": "m", "rationale": "r"}, False, []),
        ("gate_review.v1", {"project_id": "PROJ-31", "gate": "G3-execution", "decision": "fail",
                            "checklist": [], "conditions": []}, True,
         ["gate.failed", "approval.requested"]),
        ("gate_review.v1", {"project_id": "PROJ-22", "gate": "G2-planning", "decision": "pass",
                            "checklist": [], "conditions": []}, False, []),
        ("report.v1", {"scope": "PORTFOLIO#2026-Q1", "executive_summary": "ok",
                       "project_status": []}, False, ["report.generated"]),
    ],
)
def test_message_to_event_mapping(schema, data, gated, expected):
    events = events_from_message(_message(schema, data, gated=gated), gated)
    assert [e.type.value for e in events] == expected


def test_events_follow_the_active_language():
    data = {"project_id": "PROJ-31", "severity": "high", "signal": "s", "mitigation": "m",
            "rationale": "r"}
    with use_lang("ko"):
        (event,) = events_from_message(_message("risk_alert.v1", data), False)
    assert "리스크" in event.title
    resolved = approval_resolved_event({"approval_id": 3, "decision": "approve",
                                        "approver": "pm@example.com"})
    assert resolved.type is EventType.APPROVAL_RESOLVED and "approved" in resolved.title


# ── notifiers ────────────────────────────────────────────────────
@pytest.mark.regression
def test_slack_payload_shape():
    sent: list[httpx.Request] = []
    slack = SlackNotifier("https://hooks.slack.test/x", client=_capture_client(sent))
    event = Event(type=EventType.RISK_DETECTED, title="HIGH risk on PROJ-31",
                  summary="slack -7d", task_ref="PORTFOLIO#2026-Q1/PROJ-31",
                  url="http://localhost:3000/")
    slack.send(event)
    body = json.loads(sent[0].content)
    assert sent[0].url == "https://hooks.slack.test/x"
    assert body["text"] == ":rotating_light: HIGH risk on PROJ-31"
    assert [b["type"] for b in body["blocks"]] == ["header", "section", "context", "actions"]
    assert body["blocks"][3]["elements"][0]["url"] == "http://localhost:3000/"


@pytest.mark.regression
def test_webhook_payload_shape():
    sent: list[httpx.Request] = []
    hook = WebhookNotifier("https://example.test/hook", client=_capture_client(sent))
    hook.send(Event(type=EventType.REPORT_GENERATED, title="t", summary="s"))
    body = json.loads(sent[0].content)
    assert body["source"] == "ma-pmo"
    assert set(body["event"]) == {"type", "title", "summary", "severity", "task_ref", "url",
                                  "data", "occurred_at"}
    assert body["event"]["type"] == "report.generated"


def test_http_errors_surface_to_the_dispatcher():
    slack = SlackNotifier("https://hooks.slack.test/x", client=_capture_client([], status=500))
    results = dispatch.emit([Event(type=EventType.TEST, title="t", summary="")],
                            notifiers=[slack], settings=_settings())
    assert results == [{"integration": "slack", "event": "integration.test", "ok": False,
                        "error": results[0]["error"]}]


# ── dispatch ─────────────────────────────────────────────────────
@pytest.mark.regression
def test_failing_notifier_is_isolated():
    good, bad = Recorder("good"), Recorder("bad", fail=True)
    event = Event(type=EventType.RISK_DETECTED, title="t", summary="s")
    results = dispatch.emit([event], notifiers=[bad, good], settings=_settings())
    assert [r["ok"] for r in results] == [False, True]
    assert good.events == [event]


def test_event_filter():
    rec = Recorder()
    s = _settings(MA_PMO_NOTIFY_EVENTS="approval.requested")
    events = [Event(type=EventType.REPORT_GENERATED, title="r", summary=""),
              Event(type=EventType.APPROVAL_REQUESTED, title="a", summary=""),
              Event(type=EventType.TEST, title="test", summary="")]
    dispatch.emit(events, notifiers=[rec], settings=s)
    assert [e.type for e in rec.events] == [EventType.APPROVAL_REQUESTED, EventType.TEST]


# ── Jira ─────────────────────────────────────────────────────────
JIRA_PAGES = [
    {
        "issues": [
            {"key": "PAY-1", "fields": {
                "created": "2026-01-05T09:00:00.000+0900", "duedate": "2026-01-20",
                "timeoriginalestimate": 57600, "status": {"statusCategory": {"key": "done"}},
                "components": [{"name": "backend"}], "issuelinks": []}},
            {"key": "PAY-2", "fields": {
                "created": "2026-01-06T09:00:00.000+0900", "duedate": "2099-02-10",
                "timeoriginalestimate": None, "story_points": 3,
                "status": {"statusCategory": {"key": "indeterminate"}},
                "aggregateprogress": {"percent": 40}, "components": [],
                "issuelinks": [{"type": {"inward": "is blocked by", "outward": "blocks"},
                                "inwardIssue": {"key": "PAY-3"}}]}},
        ],
        "nextPageToken": "page2",
        "isLast": False,
    },
    {
        "issues": [
            {"key": "PAY-3", "fields": {
                "created": "2026-01-07T09:00:00.000+0900", "duedate": None,
                "status": {"statusCategory": {"key": "new"}}, "issuelinks": []}},
        ],
        "isLast": True,
    },
]


@pytest.mark.regression
def test_jira_tracker_maps_issues_to_portfolio_status():
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        page = 1 if request.url.params.get("nextPageToken") == "page2" else 0
        return httpx.Response(200, json=JIRA_PAGES[page])

    tracker = JiraTracker("https://acme.atlassian.net/", "pm@acme.test", "token", ["PAY"],
                          story_points_field="story_points",
                          client=httpx.Client(transport=httpx.MockTransport(handler)))
    status = tracker.get_portfolio_status("PORTFOLIO#JIRA")

    assert len(calls) == 2 and calls[0].url.path == "/rest/api/3/search/jql"
    assert 'project = "PAY"' in calls[0].url.params["jql"]
    (project,) = status["projects"]
    assert project == {
        "project_id": "PAY",
        "skill": "backend",
        "status": "amber",  # PAY-2 is blocked by unfinished PAY-3
        "planned_start": "2026-01-05",
        "planned_finish": "2099-02-10",
        "deadline": "2099-02-10",
        "percent_complete": round((16 * 100 + 24 * 40 + 8 * 0) / 48, 1),
        "tasks": [
            {"task_id": "PAY-1", "wbs": "PAY-1", "effort": 16.0, "deps": [],
             "percent_complete": 100.0},
            {"task_id": "PAY-2", "wbs": "PAY-2", "effort": 24.0, "deps": ["PAY-3"],
             "percent_complete": 40.0},
            {"task_id": "PAY-3", "wbs": "PAY-3", "effort": 8.0, "deps": [],
             "percent_complete": 0.0},
        ],
    }


def test_jira_overdue_open_issue_turns_project_red():
    page = {"issues": [{"key": "OPS-1", "fields": {
        "created": "2025-01-01T00:00:00.000+0000", "duedate": "2025-02-01",
        "status": {"statusCategory": {"key": "indeterminate"}}, "issuelinks": []}}],
        "isLast": True}
    tracker = JiraTracker("https://acme.atlassian.net", "e", "t", ["OPS"],
                          client=httpx.Client(transport=httpx.MockTransport(
                              lambda r: httpx.Response(200, json=page))))
    assert tracker.get_portfolio_status("P")["projects"][0]["status"] == "red"


def test_agents_run_on_a_jira_style_tracker():
    """Agents only need get_portfolio_status, so a Jira-shaped tracker plugs straight in."""
    from ma_pmo.agents.planning import PlanningAgent

    page = JIRA_PAGES[1] | {"issues": JIRA_PAGES[0]["issues"] + JIRA_PAGES[1]["issues"]}
    tracker = JiraTracker("https://acme.atlassian.net", "e", "t", ["PAY"],
                          story_points_field="story_points",
                          client=httpx.Client(transport=httpx.MockTransport(
                              lambda r: httpx.Response(200, json=page))))
    result = PlanningAgent(tracker=tracker).run({"task_ref": "PORTFOLIO#JIRA"})
    (out,) = result["outputs"]
    assert out["data"]["project_id"] == "PAY"
    assert out["data"]["critical_path"]
