"""Smoke tests — the app boots, every main endpoint answers, and the pipeline runs end to end
with integrations switched on. Run alone with `make test-smoke` (a few seconds)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from ma_pmo import __version__
from ma_pmo.api.main import app
from ma_pmo.cli import main as cli_main
from ma_pmo.integrations import dispatch

pytestmark = pytest.mark.smoke

client = TestClient(app)


def test_cli_version(capsys):
    with pytest.raises(SystemExit) as exc:
        cli_main(["--version"])
    assert exc.value.code == 0
    assert __version__ in capsys.readouterr().out


@pytest.mark.parametrize(
    "path",
    [
        "/health",
        "/portfolio/PORTFOLIO%232026-Q1",
        "/kpi",
        "/risks",
        "/allocations",
        "/messages",
        "/approvals",
        "/scenarios",
        "/scenarios?lang=ko",
        "/integrations",
        "/knowledge/search?q=data%20migration%20delay",
    ],
)
def test_get_endpoints_respond(path):
    resp = client.get(path)
    assert resp.status_code == 200, resp.text


def test_deterministic_agents_respond():
    assert client.post("/plan").status_code == 200
    assert client.post("/allocate").status_code == 200
    assert client.post("/gate-review?gate=G2-planning").status_code == 200


def test_orchestration_end_to_end_offline():
    resp = client.post("/orchestrate", json={"goal": "resource allocation and schedule check"})
    assert resp.status_code == 200
    body = resp.json()
    assert {d["agent"] for d in body["routing"]["delegations"]} >= {"A2", "A3"}
    assert body["synthesis"]["summary"]


def test_pipeline_emits_integration_events(monkeypatch):
    """With a notifier enabled, a high-risk scenario produces risk and approval events, and
    a notifier that crashes does not stop the scenario."""
    received = []

    class Recorder:
        name = "recorder"

        def send(self, event):
            received.append(event.type.value)

    class Broken:
        name = "broken"

        def send(self, event):
            raise RuntimeError("network down")

    monkeypatch.setattr(dispatch, "build_notifiers", lambda settings: [Broken(), Recorder()])
    resp = client.post("/scenarios/risk_escalation/run")
    assert resp.status_code == 200
    assert resp.json()["phases"][-1]["phase"] == "insight"
    assert "risk.detected" in received
    assert "approval.requested" in received


def test_integration_test_endpoint_validates_input():
    assert client.post("/integrations/does-not-exist/test").status_code == 404
    assert client.post("/integrations/jira/test").status_code == 400  # a tracker, not a notifier
    assert client.post("/integrations/slack/test").status_code == 400  # webhook URL not set
