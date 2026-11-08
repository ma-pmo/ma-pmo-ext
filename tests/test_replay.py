"""Replay evaluator: cost and quality of a step on the fast model, and approval into a draft."""
from __future__ import annotations

import json
import re

import litellm
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select

from ma_pmo.api.auth import ApiKeyAuthenticator, AuthMiddleware
from ma_pmo.api.main import app, language
from ma_pmo.api.routers import recommendations as recommendations_router
from ma_pmo.cli import main as cli
from ma_pmo.core import budgets, llm, replay, scenarios, workflow_store
from ma_pmo.core.config import get_settings
from ma_pmo.db import workspaces
from ma_pmo.db.models import Budget, LlmCall, Recommendation, Run, WorkflowVersion
from ma_pmo.db.session import get_session

client = TestClient(app)
STANDARD, FAST = get_settings().llm_model, get_settings().llm_model_fast
LABELS = {"PROJ-14": "medium", "PROJ-22": "low", "PROJ-31": "high"}
FLOW, STEP = "risk_escalation", "A4"  # A4 -> A6 -> A5; A4 rates each flagged project


@pytest.fixture(autouse=True)
def clean():
    yield
    with get_session() as s:
        for model in (Recommendation, LlmCall, Budget, WorkflowVersion):
            s.execute(delete(model))


def _provider(monkeypatch, fast: str = "good") -> None:
    """The standard model rates risks right; the fast one is `good`, `broken` or `wrong`."""

    def completion(**kw):
        user = kw["messages"][-1]["content"]
        found = re.search(r"Project: (\S+)", user)
        if found is None:  # not a risk rating (e.g. A5's report): an unusable answer
            content = "{}"
        elif kw["model"] == FAST and fast == "broken":
            content = "sorry, I cannot do that"
        else:
            project = found.group(1)
            severity = LABELS.get(project, "low")
            if kw["model"] == FAST and fast == "wrong":
                severity = "low" if severity != "low" else "high"
            content = json.dumps({"project_id": project, "signal": "slack", "severity": severity,
                                  "mitigation": "re-plan", "rationale": "signals"})
        response = litellm.ModelResponse(model=kw["model"], usage=litellm.Usage(
            prompt_tokens=1500, completion_tokens=300, total_tokens=1800))
        response.choices[0].message.content = content
        return response

    monkeypatch.setattr(llm.litellm, "completion", completion)


def _runs() -> int:
    with get_session() as s:
        return s.scalar(select(func.count()).select_from(Run)) or 0


def test_an_equally_good_cheaper_model_is_recommended(monkeypatch):
    _provider(monkeypatch, "good")
    before, spaces = _runs(), workspaces.list_all()
    rec = replay.replay(FLOW, STEP, repeat=3, by="tester")
    report = rec["report"]
    assert rec["verdict"] == "recommended" and rec["status"] == "proposed"
    assert report["models"] == {"baseline": STANDARD, "candidate": FAST}
    for metric in ("valid_output", "risk_accuracy"):
        q = report["quality"][metric]
        assert q["baseline"] == q["candidate"] == 1.0 and q["ci95"] == [0.0, 0.0]
    cost = report["cost"]
    assert cost["candidate"] < cost["baseline"] and cost["ci95"][1] < 0
    assert report["saving_pct"] > 0 and len(report["runs"]["baseline"]) == 3
    # the real workspace has no new run and no leftover sandbox, but keeps the spend
    assert _runs() == before and workspaces.list_all() == spaces
    with get_session() as s:
        purposes = set(s.scalars(select(LlmCall.purpose)))
    assert purposes == {"replay"}
    by_purpose = client.get("/costs", params={"by": "purpose"}).json()
    assert [r["key"] for r in by_purpose["rows"]] == ["replay"]


def test_a_model_that_breaks_the_output_is_not_recommended(monkeypatch):
    _provider(monkeypatch, "broken")
    rec = replay.replay(FLOW, STEP, repeat=3)
    valid = rec["report"]["quality"]["valid_output"]
    assert rec["verdict"] == "not_recommended"
    assert valid["baseline"] == 1.0 and valid["candidate"] == 0.0 and valid["ci95"][1] < 0
    assert {"code": "quality_drop", "metric": "valid_output", "tolerance": 0.05} in \
        rec["report"]["reasons"]


def test_a_model_that_misjudges_risk_is_not_recommended(monkeypatch):
    _provider(monkeypatch, "wrong")
    rec = replay.replay(FLOW, STEP, repeat=3)
    q = rec["report"]["quality"]
    assert q["valid_output"]["delta"] == 0 and q["risk_accuracy"]["delta"] < 0
    assert rec["verdict"] == "not_recommended"
    assert [r["metric"] for r in rec["report"]["reasons"]] == ["risk_accuracy"]


def test_without_an_llm_there_is_nothing_to_compare(monkeypatch):
    def down(**kw):
        raise RuntimeError("no key")

    monkeypatch.setattr(llm.litellm, "completion", down)
    rec = replay.replay(FLOW, STEP, repeat=2)
    assert rec["verdict"] == "inconclusive"
    assert rec["report"]["quality"] == {"valid_output": None, "risk_accuracy": None}
    assert rec["report"]["reasons"] == [{"code": "no_output"}]
    assert "API" in replay.reason_text({"code": "no_output"})


def test_the_budget_of_the_workspace_applies_to_a_replay(monkeypatch):
    _provider(monkeypatch, "good")
    budgets.set_budget("month", None, 0, "test")
    rec = replay.replay(FLOW, STEP, repeat=2)
    assert rec["verdict"] == "inconclusive" and rec["report"]["stopped_by_budget"] is True
    with get_session() as s:
        assert s.scalar(select(func.count()).select_from(LlmCall)) == 0


def test_approving_makes_a_draft_and_publishing_stays_separate(monkeypatch):
    _provider(monkeypatch, "good")
    rec = replay.replay(FLOW, STEP, repeat=2)
    done = replay.decide(rec["id"], "approved", "pm")
    assert done["status"] == "approved" and done["draft_version"] == 2
    assert scenarios.workflow(FLOW).version == 1  # nothing in use changed
    draft = workflow_store.spec_of(FLOW, 2)
    assert {s.id: s.model_tier for s in draft.steps}[STEP] == "fast"
    with pytest.raises(ValueError, match="already approved"):
        replay.decide(rec["id"], "approved", "pm")

    _provider(monkeypatch, "broken")
    bad = replay.replay(FLOW, STEP, repeat=2)
    with pytest.raises(ValueError, match="only a recommended"):
        replay.decide(bad["id"], "approved", "pm")
    assert replay.decide(bad["id"], "rejected", "pm")["status"] == "rejected"


def test_a_stale_recommendation_cannot_be_approved(monkeypatch):
    _provider(monkeypatch, "good")
    rec = replay.replay(FLOW, STEP, repeat=2)
    workflow_store.publish(FLOW, workflow_store.save_draft(
        scenarios.loaded(FLOW).model_dump(), "someone")["version"], "someone")
    with pytest.raises(ValueError, match="changed since the replay"):
        replay.decide(rec["id"], "approved", "pm")


def test_bad_requests_are_refused(monkeypatch):
    _provider(monkeypatch, "good")
    with pytest.raises(KeyError):
        replay.replay(FLOW, "nope")
    with pytest.raises(ValueError, match="between 2 and 50"):
        replay.replay(FLOW, STEP, repeat=1)


def test_the_api_runs_lists_and_decides_with_the_right_roles(monkeypatch):
    _provider(monkeypatch, "good")
    keys = "op:operator:operator-key-0123456789,ap:approver:approver-key-0123456789"
    secured = FastAPI()
    secured.add_middleware(AuthMiddleware, authenticator=ApiKeyAuthenticator.parse(keys))
    secured.middleware("http")(language)
    secured.include_router(recommendations_router.router)
    api = TestClient(secured)
    op, ap = {"X-API-Key": "operator-key-0123456789"}, {"X-API-Key": "approver-key-0123456789"}
    made = api.post("/recommendations/replay",
                    json={"workflow_id": FLOW, "step_id": STEP, "repeat": 2}, headers=op)
    assert made.status_code == 201 and made.json()["created_by"] == "op"
    rid = made.json()["id"]
    assert api.get("/recommendations", headers=op).json()[0]["id"] == rid
    assert api.post(f"/recommendations/{rid}/approve", headers=op).status_code == 403
    approved = api.post(f"/recommendations/{rid}/approve", headers=ap)
    assert approved.status_code == 200 and approved.json()["decided_by"] == "ap"
    again = client.post(f"/recommendations/{rid}/reject", params={"lang": "ko"})
    assert again.status_code == 409 and "이미" in again.json()["detail"]
    missing = client.post("/recommendations/replay",
                          json={"workflow_id": FLOW, "step_id": "nope", "repeat": 2})
    assert missing.status_code == 404
    assert client.post("/recommendations/999/approve").status_code == 404


def test_the_cli_replays_and_decides(monkeypatch, capsys):
    _provider(monkeypatch, "good")
    assert cli(["replay", FLOW, STEP, "--repeat", "2"]) == 0
    out = capsys.readouterr().out
    assert "recommended" in out and "valid_output" in out and "95%" in out
    assert "quality holds within 5%" in out
    rid = replay.recommendations()[0]["id"]
    assert cli(["recommendation", "approve", str(rid)]) == 0
    assert cli(["recommendation", "approve", str(rid)]) == 1
    assert cli(["recommendation", "list"]) == 0
    assert "approved" in capsys.readouterr().out
