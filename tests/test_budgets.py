"""Budgets: warn once, then stop calling the LLM, and never fail the run."""
from __future__ import annotations

import litellm
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from litellm.llms.anthropic.chat.transformation import AnthropicConfig
from sqlalchemy import delete, func, select

from ma_pmo.api.auth import ApiKeyAuthenticator, AuthMiddleware
from ma_pmo.api.main import app, language
from ma_pmo.api.routers import budgets as budgets_router
from ma_pmo.cli import main as cli
from ma_pmo.core import budgets, costs, llm, runs, workspace
from ma_pmo.core.goals import run_goal
from ma_pmo.core.scenarios import run_scenario
from ma_pmo.db import workspaces
from ma_pmo.db.models import Budget, LlmCall
from ma_pmo.db.session import get_session
from ma_pmo.integrations import registry

client = TestClient(app)
MODEL = "anthropic/claude-sonnet-5"
USAGE = {"input_tokens": 2000, "output_tokens": 500,
         "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}  # $0.009 a call


@pytest.fixture(autouse=True)
def clean():
    yield
    with get_session() as s:
        s.execute(delete(Budget))
        s.execute(delete(LlmCall))


@pytest.fixture
def calls(monkeypatch) -> list[str]:
    """Stand-in for the provider: every call is priced and counted."""
    made: list[str] = []

    def completion(**kw):
        made.append(kw["model"])
        response = litellm.ModelResponse(model="claude-sonnet-5",
                                         usage=AnthropicConfig().calculate_usage(USAGE, None))
        response.choices[0].message.content = "{}"
        return response

    monkeypatch.setattr(llm.litellm, "completion", completion)
    return made


@pytest.fixture
def notices(monkeypatch) -> list:
    sent: list = []

    class Notifier:
        name = "recorder"

        def send(self, event):
            sent.append(event)

    monkeypatch.setattr(registry, "build_notifiers", lambda settings=None: [Notifier()])
    monkeypatch.setattr("ma_pmo.integrations.dispatch.build_notifiers",
                        lambda settings=None: [Notifier()])
    return sent


def _ledger() -> int:
    with get_session() as s:
        return s.scalar(select(func.count()).select_from(LlmCall)) or 0


def test_without_a_budget_every_call_is_made(calls):
    trace = run_scenario("risk_escalation")
    assert calls and _ledger() == len(calls) and trace["budget_fallback"] is None


def test_a_run_over_its_hard_limit_falls_back_and_still_succeeds(calls):
    run_scenario("risk_escalation")
    unlimited = len(calls)
    calls.clear()
    budgets.set_budget("run", None, 0.02, "test")  # room for about two calls
    trace = run_scenario("risk_escalation")
    assert trace["status"] == "succeeded"
    assert [p["phase"] for p in trace["phases"]][-2:] == ["complete", "insight"]
    assert 0 < len(calls) < unlimited
    mark = trace["budget_fallback"]
    assert mark["kind"] == "run" and mark["limit_usd"] == 0.02 and mark["spent_usd"] >= 0.02
    assert mark["step"] in {1, 2, 3} and mark["agent"] in {"A4", "A5", "A6"}
    run = runs.get_run(trace["run_id"])
    assert run["status"] == "succeeded" and run["budget_fallback"] == mark
    listed = client.get("/runs").json()[0]
    assert listed["run_id"] == trace["run_id"] and listed["budget_fallback"]["kind"] == "run"
    # the run budget is per run: the next run starts again
    calls.clear()
    assert run_scenario("risk_escalation")["status"] == "succeeded" and calls


def test_a_zero_limit_means_no_llm_call_at_all_and_nothing_fails(calls):
    budgets.set_budget("month", None, 0, "test")
    trace = run_scenario("executive_briefing")
    goal = run_goal("risk review and report", "PORTFOLIO#2026-Q1")
    assert calls == [] and trace["status"] == goal["status"] == "succeeded"
    assert trace["budget_fallback"]["kind"] == "month"
    assert goal["budget_fallback"]["kind"] == "month" and goal["synthesis"]
    answer = client.post("/knowledge/ask", json={"query": "data migration delay"})
    assert answer.status_code == 200 and answer.json()["answer"]  # outside a run, too


def test_the_month_counts_what_was_already_spent(calls):
    costs.record(MODEL, "A5", costs.Usage(prompt=1_000_000, completion=0), 1.0)  # $2
    budgets.set_budget("month", 1.0, 2.0, "test")
    run_scenario("weekly_status")
    assert calls == []
    assert client.get("/budgets").json()["month"]["spent_usd"] == pytest.approx(2.0)


def test_warnings_are_sent_once(calls, notices):
    budgets.set_budget("month", 0.001, None, "test")
    run_scenario("risk_escalation")
    run_scenario("weekly_status")
    month = [e for e in notices if e.type.value == "budget.warning" and e.data["kind"] == "month"]
    assert len(month) == 1 and len(calls) > 2  # a warning does not stop anything
    budgets.set_budget("run", 0.001, None, "test")
    first, second = run_scenario("risk_escalation"), run_scenario("weekly_status")
    per_run = [e.task_ref for e in notices if e.data.get("kind") == "run"]
    assert sorted(per_run) == sorted([first["run_id"], second["run_id"]])


def test_budgets_are_checked_and_need_an_admin():
    keys = "op:operator:operator-key-0123456789,ad:admin:admin-key-0123456789"
    secured = FastAPI()
    secured.add_middleware(AuthMiddleware, authenticator=ApiKeyAuthenticator.parse(keys))
    secured.middleware("http")(language)
    secured.include_router(budgets_router.router)
    api = TestClient(secured)
    body = {"warn_usd": 50, "limit_usd": 100}
    assert api.get("/budgets", headers={"X-API-Key": "operator-key-0123456789"}).status_code == 200
    assert api.put("/budgets/month", json=body,
                   headers={"X-API-Key": "operator-key-0123456789"}).status_code == 403
    done = api.put("/budgets/month", json=body, headers={"X-API-Key": "admin-key-0123456789"})
    assert done.status_code == 200 and done.json()["month"]["limit_usd"] == 100
    for bad in ({"warn_usd": 5, "limit_usd": 1}, {"limit_usd": -1}):
        assert client.put("/budgets/run", json=bad).status_code == 422
    assert client.put("/budgets/week", json=body).status_code == 422
    korean = client.put("/budgets/run?lang=ko", json={"warn_usd": 5, "limit_usd": 1})
    assert "한도보다" in korean.json()["detail"]
    cleared = client.put("/budgets/month", json={})
    assert cleared.json()["month"]["limit_usd"] is None


def test_each_workspace_has_its_own_budget(calls):
    workspaces.create("acme-budget", "Acme")
    try:
        with workspace.use("acme-budget"):
            budgets.set_budget("month", None, 0, "test")
            run_scenario("weekly_status")
            assert calls == []
        run_scenario("weekly_status")
        assert calls
    finally:
        from ma_pmo.core.dry_run import _erase

        _erase("acme-budget")  # the run there left runs, messages, reports and KPIs


def test_the_cli_shows_and_sets_budgets(capsys):
    assert cli(["budget", "set", "month", "--warn", "40", "--limit", "50"]) == 0
    assert cli(["budget", "set", "run"]) == 1
    assert cli(["budget", "set", "run", "--warn", "3", "--limit", "1"]) == 1
    assert cli(["budget", "show"]) == 0
    assert cli(["budget", "clear", "month"]) == 0
    out = capsys.readouterr().out
    assert "limit $50.00" in out and "warning must not be above" in out
    assert budgets.status()["month"]["limit_usd"] is None
