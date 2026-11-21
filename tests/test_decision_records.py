"""Roadmap 8, step 2: each decision leaves a record of who decided what, why, whom they asked."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from ma_pmo.api.main import app
from ma_pmo.core import budgets, decisions, hitl
from ma_pmo.core.scenarios import run_scenario

client = TestClient(app)


def test_the_commit_gate_records_each_decision_with_its_reviewers():
    trace = run_scenario("go_nogo_decision")
    found = decisions.list_records(limit=500)
    mine = [r for r in found if r["run_id"] == trace["run_id"]]
    assert len(mine) == len(trace["commit"])
    by_message = {r["message_id"]: r for r in mine}
    for item in trace["commit"]:
        rec = by_message[item["message_id"]]
        assert rec["status"] in {"committed", "proposed"}
        assert (rec["status"] == "committed") == (item["status"] == "committed")
        assert rec["decision_makers"][0]["role"] == "proposer"
        assert rec["options"][0]["message_id"] == item["message_id"]
    assert any(r["consulted"] and all(c["verdict"] for c in r["consulted"]) for r in mine)
    gates = [r for r in mine if r["kind"] == "gate"]
    assert gates and all("/" in r["subject"] for r in gates)


def test_a_later_decision_on_the_same_subject_supersedes_the_earlier_one():
    first = decisions.record("budget", "test-subject", "one", "accepted")
    second = decisions.record("budget", "test-subject", "two", "accepted")
    assert second["supersedes"] == first["id"]
    assert decisions.get(first["id"])["status"] == "superseded"


def test_rejecting_needs_a_reason_and_records_it():
    trace = run_scenario("risk_escalation", pause_on_gate=True)
    approval_id = trace["pending_approvals"][0]
    with pytest.raises(ValueError, match="reason is required"):
        hitl.resolve(approval_id, approver="pm", decision="reject")
    resp = client.post(f"/approvals/{approval_id}", json={"approver": "pm", "decision": "reject"})
    assert resp.status_code == 400
    done = hitl.resolve(approval_id, approver="pm", decision="reject", rationale="  too risky ")
    assert done["rationale"] == "too risky"
    rec = client.get(f"/decisions/{done['decision_record']}").json()
    assert rec["status"] == "rejected" and rec["approval_id"] == approval_id
    assert rec["outcome"] == {"chosen": "reject", "justification": "too risky"}
    assert {"who": "pm", "role": "approver"} in rec["decision_makers"]


def test_approving_an_unchallenged_item_needs_no_reason():
    trace = run_scenario("risk_escalation", pause_on_gate=True)
    done = hitl.resolve(trace["pending_approvals"][0], approver="pm", decision="approve")
    assert done["rationale"] is None
    assert decisions.get(done["decision_record"])["status"] == "accepted"


def test_a_budget_change_is_a_decision_and_the_log_filters():
    budgets.set_budget(budgets.MONTH, 5.0, 10.0, by="finance")
    listed = client.get("/decisions", params={"kind": "budget", "subject": budgets.MONTH}).json()
    assert listed and listed[0]["decision_makers"] == [{"who": "finance", "role": "decider"}]
    assert listed[0]["status"] == "accepted"
    budgets.set_budget(budgets.MONTH, None, None, by="finance")
    assert client.get("/decisions/DEC-missing").status_code == 404
