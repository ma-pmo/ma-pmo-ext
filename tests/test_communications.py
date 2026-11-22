"""Roadmap 8, step 3: every notification attempt is logged, sent, failed or skipped with why."""
from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from ma_pmo.api.main import app
from ma_pmo.core import communications, hitl, runs, workspace
from ma_pmo.core.config import Settings
from ma_pmo.core.scenarios import run_scenario
from ma_pmo.integrations import dispatch, registry
from ma_pmo.integrations.base import Event, EventType

client = TestClient(app)


def _settings(**env: str) -> Settings:
    return Settings(_env_file=None, **env)  # type: ignore[call-arg]


class Recorder:
    def __init__(self, name: str, fail: bool = False) -> None:
        self.name, self.fail = name, fail

    def send(self, event: Event) -> None:
        if self.fail:
            raise RuntimeError("boom")


def _event(kind: EventType = EventType.RISK_DETECTED, **data) -> tuple[Event, str]:
    mark = f"msg-{uuid.uuid4().hex[:8]}"
    return Event(type=kind, title="t", summary="s", task_ref="P/PROJ-31",
                 data={"message_id": mark, **data}), mark


def test_each_attempt_is_logged_with_its_outcome():
    event, mark = _event()
    dispatch.emit([event], notifiers=[Recorder("bad", fail=True), Recorder("good")],
                  settings=_settings())
    rows = communications.list_log(message=mark)
    assert {(r["channel"], r["status"]) for r in rows} == {("bad", "failed"), ("good", "sent")}
    assert next(r for r in rows if r["status"] == "failed")["error"] == "boom"
    assert all(r["event"] == "risk.detected" and r["target"] == "P/PROJ-31" for r in rows)


def test_deliberate_skips_are_logged_with_the_reason():
    quiet, a = _event()
    dispatch.emit([quiet], notifiers=[], settings=_settings())
    with registry.demo_only():
        dry, b = _event()
        dispatch.emit([dry], notifiers=[Recorder("good")], settings=_settings())
    other, c = _event(EventType.REPORT_GENERATED)
    dispatch.emit([other], notifiers=[Recorder("good")],
                  settings=_settings(MA_PMO_NOTIFY_EVENTS="approval.requested"))
    reasons = {m: communications.list_log(message=m)[0] for m in (a, b, c)}
    assert all(r["status"] == "skipped" and r["channel"] == "-" for r in reasons.values())
    assert reasons[a]["error"] == "no notifier configured"
    assert reasons[b]["error"] == "dry run"
    assert reasons[c]["error"].startswith("not subscribed")


def test_background_delivery_keeps_the_callers_workspace_and_run(monkeypatch):
    monkeypatch.setattr(dispatch, "build_notifiers", lambda settings: [Recorder("good")])
    event, mark = _event()
    token = runs._current_run.set("run-bg-test")
    try:
        dispatch.emit_later([event])
    finally:
        runs._current_run.reset(token)
    assert dispatch.flush(timeout=5)
    (row,) = communications.list_log(message=mark)
    assert row["status"] == "sent" and row["run_id"] == "run-bg-test"
    with workspace.use("elsewhere"):  # written in the caller's workspace, not another
        assert communications.list_log(message=mark) == []


def test_a_decision_lists_whom_it_was_told_to():
    trace = run_scenario("risk_escalation", pause_on_gate=True)
    assert dispatch.flush(timeout=5)
    logged = client.get("/communications", params={"run": trace["run_id"]}).json()
    assert logged and {r["event"] for r in logged} >= {"risk.detected", "approval.requested"}
    done = hitl.resolve(trace["pending_approvals"][0], approver="pm", decision="reject",
                        rationale="not now")
    assert dispatch.flush(timeout=5)
    rec = client.get(f"/decisions/{done['decision_record']}").json()
    told = {(i["event"], i["status"]) for i in rec["informed"]}
    assert ("approval.requested", "skipped") in told  # no notifier is set up in the tests
    assert ("approval.resolved", "skipped") in told
