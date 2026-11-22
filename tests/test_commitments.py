"""Roadmap 9, step 1: the obligations a decision creates become commitments with a state."""
from __future__ import annotations

import copy

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

from ma_pmo.api.main import app
from ma_pmo.core import commitments, hitl, protocol
from ma_pmo.core.config import get_settings
from ma_pmo.core.scenarios import run_scenario
from ma_pmo.core.schemas.message import AgentMessage, Intent, MessagePayload
from ma_pmo.db.models import Commitment
from ma_pmo.db.session import get_session
from ma_pmo.integrations.registry import get_tracker

client = TestClient(app)


@pytest.fixture(autouse=True)
def _as_of(monkeypatch):
    """The demo data's own week: PROJ-14 and PROJ-31 pass G3 on condition (blocked tasks)."""
    monkeypatch.setattr(get_settings(), "report_as_of", "2026-02-16")
    yield
    with get_session() as s:  # due in the demo week: overdue for later tests' sweeps
        s.execute(delete(Commitment))


def _conditional_gate() -> dict:
    """A conditional gate waiting for a person (go/no-go on the demo data)."""
    ours = {c["message_id"] for c in run_scenario("go_nogo_decision")["commit"]}
    return next(p for p in hitl.list_pending() if p["message_id"] in ours
                and p["payload"]["data"]["decision"] == "conditional")


def test_operations_follow_the_commitment_states():
    c = commitments.create(kind="approval_condition", debtor="team", creditor="pm",
                           consequent="send the plan", by="pm")
    assert c["state"] == "active" and c["due"].startswith("2026-03-02")  # as-of + 14 days
    done = commitments.apply(c["id"], "discharge", by="team", evidence=[{"kind": "reference",
                                                                         "ref": "DOC-1"}])
    assert done["state"] == "satisfied" and done["evidence"][0]["ref"] == "DOC-1"
    with pytest.raises(ValueError):
        commitments.apply(c["id"], "discharge", by="team")
    cancelled = commitments.create(kind="approval_condition", debtor="team", creditor="pm",
                                   consequent="x", by="pm")
    assert commitments.apply(cancelled["id"], "cancel", by="team")["state"] == "violated"
    later = commitments.create(kind="approval_condition", debtor="team", creditor="pm",
                               consequent="y", by="pm", antecedent="budget approved",
                               due="2026-W12")
    assert later["state"] == "conditional" and later["due"].startswith("2026-03-20")
    assert commitments.apply(later["id"], "detach", by="pm")["state"] == "active"
    moved = commitments.apply(later["id"], "delegate", by="team", to="ops team")
    moved = commitments.apply(later["id"], "assign", by="pm", to="sponsor")
    assert (moved["debtor"], moved["creditor"], moved["state"]) == ("ops team", "sponsor",
                                                                    "active")
    assert commitments.apply(later["id"], "release", by="sponsor")["state"] == "released"
    assert [h["op"] for h in commitments.get(later["id"])["history"]] == [
        "create", "detach", "delegate", "assign", "release"]
    with pytest.raises(ValueError):
        commitments.apply(c["id"], "delegate", by="x", to="")


def test_approving_a_conditional_gate_puts_its_conditions_in_force():
    gate = _conditional_gate()
    data = gate["payload"]["data"]
    done = hitl.resolve(gate["approval_id"], approver="pm", decision="approve",
                        rationale="conditions agreed")
    owed = [commitments.get(c) for c in done["commitments"]]
    assert [c["consequent"] for c in owed] == data["conditions"]
    first = owed[0]
    assert (first["kind"], first["debtor"], first["creditor"]) == (
        "gate_condition", data["project_id"], "pm")
    assert first["check"]["kind"] == "gate_criterion" and first["source_decision"]
    # each operation is a message in the gate's conversation, replying to the gate
    thread = client.get(f"/messages/{gate['message_id']}/thread").json()
    posted = [m for m in thread["messages"] if m["schema"] == "commitment.v1"]
    assert posted and all(m["in_reply_to"] == gate["message_id"] for m in posted)


def test_the_tracker_discharges_a_condition_once_its_criterion_passes():
    gate = _conditional_gate()
    done = hitl.resolve(gate["approval_id"], approver="pm", decision="approve",
                        rationale="conditions agreed")
    (cid,) = [c for c in done["commitments"]
              if "lock" in commitments.get(c)["consequent"]]  # "No blocked tasks"
    project = commitments.get(cid)["project_id"]
    real = get_tracker()

    class Unblocked:  # the predecessors the blocked tasks wait for are now finished
        def get_portfolio_status(self, scope):
            status = copy.deepcopy(real.get_portfolio_status(scope))
            for p in status["projects"]:
                if p["project_id"] == project:
                    waited = {d for t in p.get("tasks", []) for d in t.get("deps", [])}
                    for t in p.get("tasks", []):
                        if t["task_id"] in waited:
                            t["percent_complete"] = 100
            return status

    assert cid not in [c["id"] for c in commitments.check_tracker(real)]  # still blocked
    discharged = commitments.check_tracker(Unblocked())
    assert cid in [c["id"] for c in discharged]
    after = commitments.get(cid)
    assert after["state"] == "satisfied" and after["evidence"][0]["ref"] == project


def test_a_person_attaches_conditions_and_adopts_an_alternative():
    gate = _conditional_gate()
    alt = protocol.publish(AgentMessage(
        sender="A8", receiver="A1", intent=Intent.INFORM, task_ref=gate["task_ref"],
        payload=MessagePayload(schema_="review.v1", data={
            "target": gate["message_id"], "constraint": "alternative.add_capacity",
            "verdict": "ALTERNATIVE", "role": "dedicated",
            "alternative": {"kind": "add_capacity", "decision": "conditional",
                            "summary": "add 30 h/week of ml until 2026-W12",
                            "until": "2026-W12"}})))
    resp = client.post(f"/approvals/{gate['approval_id']}", json={
        "approver": "pm", "decision": "reject", "rationale": "no",
        "conditions": [{"text": "x"}]})
    assert resp.status_code == 400
    with pytest.raises(ValueError, match="not an alternative"):
        hitl.resolve(gate["approval_id"], approver="pm", decision="approve",
                     rationale="ok", adopt=[gate["message_id"]])
    assert any(p["approval_id"] == gate["approval_id"] for p in hitl.list_pending())
    done = client.post(f"/approvals/{gate['approval_id']}", json={
        "approver": "pm", "decision": "approve", "rationale": "with capacity",
        "conditions": [{"text": "weekly status to the sponsor", "due": "2026-03-06"}],
        "adopt": [alt.message_id]}).json()
    owed = {c["kind"]: c for c in (commitments.get(i) for i in done["commitments"])}
    assert owed["approval_condition"]["due"].startswith("2026-03-06")
    assert owed["alternative"]["consequent"] == "add 30 h/week of ml until 2026-W12"
    assert owed["alternative"]["due"].startswith("2026-03-20")  # the Friday of 2026-W12


def test_the_api_lists_and_operates():
    c = commitments.create(kind="approval_condition", debtor="team-api", creditor="pm",
                           consequent="z", by="pm")
    listed = client.get("/commitments", params={"debtor": "team-api"}).json()
    assert [x["id"] for x in listed] == [c["id"]]
    ok = client.post(f"/commitments/{c['id']}/discharge",
                     json={"by": "team-api", "reference": "JIRA-7"}).json()
    assert ok["state"] == "satisfied" and ok["evidence"] == [{"kind": "reference",
                                                              "ref": "JIRA-7"}]
    assert client.post(f"/commitments/{c['id']}/cancel", json={}).status_code == 400
    assert client.post(f"/commitments/{c['id']}/explode", json={}).status_code == 404
    assert client.post("/commitments/COM-none/discharge", json={}).status_code == 404
    assert client.post("/commitments/check").status_code == 200
