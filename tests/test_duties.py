"""Roadmap 10, step 4: segregation of duties on approvals."""
from __future__ import annotations

import pytest
from sqlalchemy import delete

from ma_pmo.core import duties, guardrails, hitl, policy, runs
from ma_pmo.core.config import get_settings
from ma_pmo.core.scenarios import run_scenario
from ma_pmo.db.models import Policy
from ma_pmo.db.session import get_session


@pytest.fixture(autouse=True)
def _demo_week(monkeypatch):
    monkeypatch.setattr(get_settings(), "report_as_of", "2026-02-16")
    yield
    with get_session() as s:
        s.execute(delete(Policy))


def _enforce(**params) -> None:
    policy.change({"segregation": {"mode": "enforce", "params": params}}, by="admin")


def _risk_approval(asker: str | None = None) -> dict:
    """The approval A4's high risk on PROJ-31 asks for, in a run `asker` started."""
    with duties.requested_by(asker):
        trace = run_scenario("risk_escalation")
    assert runs.get_state(trace["run_id"])["requested_by"] == asker
    ours = {m["message_id"] for m in trace["communications"]}
    return next(p for p in hitl.list_pending() if p["message_id"] in ours
                and p["payload"]["schema"] == "risk_alert.v1")


def test_observe_records_what_it_would_refuse():
    item = _risk_approval()
    done = hitl.resolve(item["approval_id"], approver="A4", decision="approve")
    assert done["decision"] == "approve"  # observe: let through
    entry = guardrails.log(name="segregation", limit=1)[0]
    assert (entry["decision"], entry["outcome"]) == ("allow", "block")
    assert "agent" in entry["reason"]


def test_agents_and_the_requester_cannot_decide():
    _enforce()
    item = _risk_approval(asker="alice")
    for who in ("A4", "due-dates"):
        with pytest.raises(duties.NotSeparated, match="only people decide"):
            hitl.resolve(item["approval_id"], approver=who, decision="approve")
    with pytest.raises(duties.NotSeparated, match="own request"):
        hitl.resolve(item["approval_id"], approver="alice", decision="reject", rationale="no")
    assert hitl.resolve(item["approval_id"], approver="bob",
                        decision="approve")["decision"] == "approve"


def test_above_the_threshold_two_people_approve():
    _enforce(two_person_severities=["high", "critical"])
    item = _risk_approval()
    first = hitl.resolve(item["approval_id"], approver="bob", decision="approve")
    assert first["status"] == "awaiting a second approver" and first["decision"] == "pending"
    still = next(p for p in hitl.list_pending() if p["approval_id"] == item["approval_id"])
    assert [s["who"] for s in still["signoffs"]] == ["bob"]
    with pytest.raises(duties.NotSeparated, match="someone else"):
        hitl.resolve(item["approval_id"], approver="bob", decision="approve")
    done = hitl.resolve(item["approval_id"], approver="carol", decision="approve")
    assert done["decision"] == "approve" and done["approver"] == "carol"
    other = _risk_approval()  # one rejection is enough
    assert hitl.resolve(other["approval_id"], approver="bob", decision="reject",
                        rationale="too risky")["decision"] == "reject"


def test_below_the_threshold_one_approval_is_enough():
    _enforce(two_person_severities=["critical"])
    item = _risk_approval()  # rated high, not critical
    assert hitl.resolve(item["approval_id"], approver="bob",
                        decision="approve")["decision"] == "approve"
