"""Roadmap 9, step 2: missed commitments become violated and escalate along a fixed chain."""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

from ma_pmo.agents.risk import RiskAgent
from ma_pmo.api.main import app
from ma_pmo.core import commitments, communications, decisions, hitl
from ma_pmo.core.config import get_settings
from ma_pmo.core.scenarios import run_scenario
from ma_pmo.db.models import Commitment
from ma_pmo.db.session import get_session
from ma_pmo.integrations import dispatch

client = TestClient(app)
AS_OF = datetime(2026, 2, 16)


@pytest.fixture(autouse=True)
def _demo_week(monkeypatch):
    monkeypatch.setattr(get_settings(), "report_as_of", "2026-02-16")
    monkeypatch.setattr(get_settings(), "commitment_escalate_days", 2)
    yield
    with get_session() as s:  # violated commitments would escalate in later tests' runs
        s.execute(delete(Commitment))


def _owed(due: str = "2026-02-10", **kw) -> dict:
    return commitments.create(kind="approval_condition", debtor="PROJ-31", creditor="pm",
                              consequent=kw.pop("consequent", "recovery plan to the sponsor"),
                              by="pm", due=due, project_id="PROJ-31", **kw)


def _gate_with_condition(due: str) -> tuple[dict, str]:
    """A conditional gate approved with one condition of ours, due on `due`."""
    ours = {c["message_id"] for c in run_scenario("go_nogo_decision")["commit"]}
    gate = next(p for p in hitl.list_pending() if p["message_id"] in ours
                and p["payload"]["data"]["decision"] == "conditional")
    done = hitl.resolve(gate["approval_id"], approver="pm", decision="approve", rationale="ok",
                        conditions=[{"text": "weekly status to the sponsor", "due": due}])
    (cid,) = [c for c in done["commitments"]
              if commitments.get(c)["kind"] == "approval_condition"]
    return gate, cid


def test_a_missed_commitment_walks_the_chain_once():
    gate, cid = _gate_with_condition("2026-02-10")
    first = commitments.sweep(AS_OF)
    assert cid in first["violated"] and cid in first["escalated"]
    c = commitments.get(cid)
    assert (c["state"], c["history"][-1]["step"]) == ("violated", "debtor")
    assert commitments.sweep(AS_OF) == {"violated": [], "expired": [], "escalated": [],
                                        "reopened": []}  # nothing twice
    assert cid in commitments.sweep(AS_OF + timedelta(days=2))["escalated"]
    assert commitments.get(cid)["history"][-1]["step"] == "accountable"
    assert cid in commitments.sweep(AS_OF + timedelta(days=4))["reopened"]
    # the gate is back in the queue, with the missed obligation as the reason
    record = decisions.get(commitments.get(cid)["source_decision"])
    assert record["status"] == "reopened" and "weekly status" in record["consequences"][-1]
    back = [p for p in hitl.list_pending() if p["message_id"] == gate["message_id"]]
    assert back and back[0]["reopened"]["commitment"] == cid
    assert commitments.sweep(AS_OF + timedelta(days=30))["reopened"] == []
    # each step was a message in the gate's conversation, and a logged notification
    assert dispatch.flush(timeout=5)
    told = {r["event"] for m in client.get(f"/messages/{gate['message_id']}/thread").json()[
        "messages"] if m["schema"] == "commitment.v1"
        for r in communications.list_log(message=m["message_id"])}
    assert told == {"commitment.violated", "commitment.escalated", "decision.reopened"}


def test_a_late_sweep_catches_up_and_release_ends_the_chain():
    late, quiet = _owed(), _owed(consequent="something else")
    commitments.sweep(AS_OF)  # both violated, debtors told
    commitments.apply(quiet["id"], "release", by="pm", note="no longer needed")
    commitments.sweep(AS_OF + timedelta(days=10))
    assert [h.get("step") for h in commitments.get(late["id"])["history"]
            if h["op"] == "escalate"] == ["debtor", "accountable", "reopen"]
    assert commitments.get(quiet["id"])["state"] == "released"
    assert commitments.get(quiet["id"])["escalation"] == 1


def test_an_antecedent_that_never_held_expires_without_escalating():
    c = commitments.create(kind="approval_condition", debtor="PROJ-31", creditor="pm",
                           consequent="hire a contractor", by="pm", antecedent="budget approved",
                           detach_by="2026-02-12", due="2026-03-01", project_id="PROJ-31")
    out = commitments.sweep(AS_OF)
    assert c["id"] in out["expired"] and c["id"] not in out["escalated"]
    assert commitments.get(c["id"])["state"] == "expired"


def test_a4_counts_what_the_project_missed():
    c = _owed(consequent="close the blocked tasks")
    commitments.sweep(AS_OF)
    assessed = RiskAgent().assess_project("PROJ-31")
    assert assessed["risk"]["severity"] in {"high", "critical"}
    assert "close the blocked tasks" in assessed["risk"]["signal"]
    commitments.apply(c["id"], "release", by="pm")
    assert "close the blocked tasks" not in RiskAgent().assess_project("PROJ-31")["risk"]["signal"]


def test_every_run_sweeps_first_and_the_api_can_sweep():
    c = _owed()
    run_scenario("weekly_status")
    assert commitments.get(c["id"])["state"] == "violated"
    other = _owed(due="2026-02-11")
    assert other["id"] in client.post("/commitments/sweep").json()["violated"]
