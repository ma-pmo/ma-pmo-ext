"""Roadmap 10, step 1: one guardrail engine, a versioned policy and a record of every check."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import delete

from ma_pmo.api.auth import required_role
from ma_pmo.api.main import app
from ma_pmo.core import budgets, decisions, guardrails, policy, protocol, runs
from ma_pmo.core.scenarios import run_scenario
from ma_pmo.core.schemas.message import AgentMessage, Intent, MessagePayload
from ma_pmo.db.models import Policy
from ma_pmo.db.session import get_session

client = TestClient(app)


@pytest.fixture(autouse=True)
def _default_policy():
    yield
    with get_session() as s:  # back to the built-in defaults
        s.execute(delete(Policy))


def _bad_gate() -> AgentMessage:
    return AgentMessage(sender="A6", receiver="A1", intent=Intent.INFORM, task_ref="T",
                        payload=MessagePayload(schema_="gate_review.v1",
                                               data={"project_id": "P", "decision": "maybe"}))


def test_the_existing_checks_are_guardrails_enforced_by_default():
    found = {g["name"]: g for g in policy.current()["guardrails"]}
    assert (found["budget"]["point"], found["budget"]["mode"]) == ("spend", "enforce")
    assert (found["schema"]["point"], found["schema"]["mode"]) == ("output", "enforce")
    assert policy.version() == 0
    bad = _bad_gate()
    with pytest.raises(ValidationError):  # as before
        protocol.publish(bad)
    (entry,) = guardrails.log(name="schema", outcome="block", limit=1)
    assert entry["decision"] == "block" and entry["message_id"] == bad.message_id
    assert entry["detail"]["schema"] == "gate_review.v1" and entry["detail"]["errors"]


def test_observe_mode_records_what_it_would_have_blocked():
    policy.change({"schema": {"mode": "observe"}}, by="admin", note="trying it out")
    bad = protocol.publish(_bad_gate())  # let through
    (entry,) = guardrails.log(name="schema", limit=1)
    assert (entry["mode"], entry["decision"], entry["outcome"]) == ("observe", "allow", "block")
    assert entry["message_id"] == bad.message_id and entry["policy_version"] == 1


def test_the_budget_is_a_guardrail(monkeypatch):
    budgets.set_budget(budgets.MONTH, None, 1.0, by="finance")
    monkeypatch.setattr(budgets, "spent_this_month", lambda: 2.5)
    try:
        with pytest.raises(budgets.BudgetExceeded):
            budgets.check("A4")
        (entry,) = guardrails.log(name="budget", limit=1)
        assert entry["point"] == "spend" and entry["decision"] == "block"
        assert entry["detail"] == {"kind": "month", "spent_usd": 2.5, "limit_usd": 1.0}
        policy.change({"budget": {"mode": "observe"}}, by="admin")
        budgets.check("A4")  # past the limit, but only observed
        assert guardrails.log(name="budget", limit=1)[0]["outcome"] == "block"
    finally:
        budgets.set_budget(budgets.MONTH, None, None, by="finance")


def test_a_policy_change_is_a_version_and_a_decision():
    with pytest.raises(ValueError, match="unknown guardrail"):
        policy.change({"nope": {"mode": "off"}}, by="admin")
    with pytest.raises(ValueError, match="mode"):
        policy.change({"schema": {"mode": "loud"}}, by="admin")
    policy.change({"schema": {"mode": "observe"}}, by="admin", note="first")
    policy.change({"budget": {"mode": "observe"}}, by="admin", note="second")
    (latest, first) = policy.versions()
    assert (latest["version"], first["version"]) == (2, 1)
    assert latest["document"]["guardrails"] == {"schema": {"mode": "observe"},
                                                "budget": {"mode": "observe"}}
    rec = decisions.list_records(kind="policy", limit=1)[0]
    assert rec["title"].startswith("policy v2") and rec["outcome"]["justification"] == "second"
    trace = run_scenario("weekly_status")  # a run keeps the version it ran under
    assert runs.get_state(trace["run_id"])["policy_version"] == 2


def test_the_api_reads_and_changes_the_policy_with_admin():
    assert required_role("PUT", "/policy") == "admin"
    assert client.get("/policy").json()["version"] == 0
    changed = client.put("/policy", json={"guardrails": {"schema": {"mode": "observe"}},
                                          "note": "api"}).json()
    assert changed["version"] == 1
    assert client.put("/policy", json={"guardrails": {"x": {}}}).status_code == 400
    assert client.get("/policy/versions").json()[0]["note"] == "api"
    assert isinstance(client.get("/guardrails", params={"point": "output"}).json(), list)
