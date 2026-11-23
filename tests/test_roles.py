"""Roadmap 9, step 4: RACI roles route approvals, name people, and own commitments."""
from __future__ import annotations

from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

from ma_pmo.api.auth import required_role
from ma_pmo.api.main import app
from ma_pmo.core import commitments, decisions, hitl, questions, roles
from ma_pmo.core.config import get_settings
from ma_pmo.core.scenarios import run_scenario
from ma_pmo.core.schemas.message import AgentMessage, Intent, MessagePayload
from ma_pmo.db.models import Commitment, RoleAssignment
from ma_pmo.db.session import get_session
from ma_pmo.integrations.events import events_from_message

client = TestClient(app)


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    monkeypatch.setattr(get_settings(), "report_as_of", "2026-02-16")
    yield
    with get_session() as s:
        s.execute(delete(RoleAssignment))
        s.execute(delete(Commitment))


def _conditional_gate() -> dict:
    ours = {c["message_id"] for c in run_scenario("go_nogo_decision")["commit"]}
    return next(p for p in hitl.list_pending() if p["message_id"] in ours
                and p["payload"]["data"]["decision"] == "conditional")


def test_the_most_specific_assignment_wins():
    roles.assign("gate", "A", "alice", project="PROJ-31")
    roles.assign("gate", "A", "bob")
    roles.assign("*", "A", "carol")
    assert roles.who("gate", "A", "PROJ-31") == ["alice"]
    assert roles.who("gate", "A", "PROJ-14") == ["bob"]
    assert roles.who("budget", "A") == ["carol"]
    assert roles.who("budget", "R") == []
    again = roles.assign("gate", "a", "alice", project="PROJ-31")  # same role twice: no-op
    assert len(roles.list_roles("gate", "PROJ-31")) == 1 and again["role"] == "A"
    with pytest.raises(ValueError):
        roles.assign("gate", "X", "dave")


def test_only_the_accountable_decide_and_records_name_people():
    roles.assign("gate", "A", "alice")
    roles.assign("gate", "C", "carl")
    roles.assign("gate", "I", "ines")
    roles.assign("gate", "R", "team-lead")
    gate = _conditional_gate()
    assert gate["accountable"] == ["alice"]
    denied = client.post(f"/approvals/{gate['approval_id']}",
                         json={"approver": "bob", "decision": "approve", "rationale": "ok"})
    assert denied.status_code == 403 and "alice" in denied.json()["detail"]
    done = hitl.resolve(gate["approval_id"], approver="alice", decision="approve",
                        rationale="conditions agreed")
    rec = decisions.get(done["decision_record"])
    assert {"who": "alice", "role": "accountable"} in rec["decision_makers"]
    assert {"who": "carl", "role": "consulted"} in rec["consulted"]
    assert {"who": "ines", "role": "informed"} in rec["informed"]
    owed = commitments.get(done["commitments"][0])
    assert (owed["debtor"], owed["creditor"]) == ("team-lead", "alice")
    # escalation goes to the Accountable
    commitments.sweep(datetime(2026, 12, 1))  # violated: the Responsible is told
    commitments.sweep(datetime(2026, 12, 3))  # two days on: the Accountable
    notes = [h["note"] for h in commitments.get(owed["id"])["history"] if h["op"] == "escalate"]
    assert notes[:2] == ["step 1: told team-lead", "step 2: told alice"]


def test_without_roles_anyone_with_the_role_decides():
    gate = _conditional_gate()
    assert gate["accountable"] == []
    assert hitl.resolve(gate["approval_id"], approver="anyone", decision="approve",
                        rationale="ok")["decision"] == "approve"


def test_questions_go_to_the_responsible_and_events_name_recipients():
    roles.assign("question", "R", "owner")
    asked = questions.ask("A2", None, None, questions.Question(
        key="PROJ-22.planned_start", ask="When?", why="dates", answer_type="date",
        default="2026-02-16", project_id="PROJ-22"))
    assert asked["debtor"] == "owner"
    roles.assign("gate", "A", "alice")
    roles.assign("gate", "C", "carl")
    gated = AgentMessage(sender="A6", receiver="A1", intent=Intent.PROPOSE,
                         task_ref="PORTFOLIO#2026-Q1/PROJ-31", human_gate_required=True,
                         payload=MessagePayload(schema_="gate_review.v1", data={
                             "project_id": "PROJ-31", "gate": "G3-execution",
                             "decision": "conditional"}))
    (requested,) = [e for e in events_from_message(gated, gated=True)
                    if e.type.value == "approval.requested"]
    assert requested.data["recipients"] == {"decide": ["alice"], "consult": ["carl"]}


def test_the_api_assigns_lists_and_removes_with_admin():
    assert required_role("POST", "/roles") == "admin"
    assert required_role("DELETE", "/roles/3") == "admin"
    made = client.post("/roles", json={"kind": "budget", "role": "A", "person": "fin"}).json()
    assert client.get("/roles", params={"kind": "budget"}).json()[0]["person"] == "fin"
    assert client.get("/roles/who", params={"kind": "budget"}).json()["A"] == ["fin"]
    assert client.post("/roles", json={"kind": "budget", "role": "Z",
                                       "person": "x"}).status_code == 400
    assert client.delete(f"/roles/{made['id']}").json() == {"removed": made["id"]}
    assert client.delete(f"/roles/{made['id']}").status_code == 404
