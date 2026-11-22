"""Roadmap 8, step 4: a decision exported as W3C PROV-JSON traces back to its evidence."""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from ma_pmo.api.main import app
from ma_pmo.core import budgets, hitl
from ma_pmo.core.scenarios import run_scenario

client = TestClient(app)
ENDS = {"wasGeneratedBy": ("entity", "activity"), "wasAttributedTo": ("entity", "agent"),
        "wasDerivedFrom": ("generatedEntity", "usedEntity"),
        "wasAssociatedWith": ("activity", "agent"), "wasInformedBy": ("informed", "informant")}
KINDS = {"entity": "entity", "generatedEntity": "entity", "usedEntity": "entity",
         "activity": "activity", "informed": "activity", "informant": "activity",
         "agent": "agent"}


def _prov(record_id: str) -> dict:
    resp = client.get(f"/decisions/{record_id}/provenance")
    assert resp.status_code == 200
    return resp.json()


def _closed(doc: dict) -> None:
    """Every relation names nodes the document declares, with known prefixes."""
    for relation, ends in ENDS.items():
        for body in doc.get(relation, {}).values():
            for end in ends:
                ident = body[f"prov:{end}"]
                assert ident.split(":", 1)[0] in doc["prefix"]
                assert ident in doc[KINDS[end]], (relation, ident)


def test_a_rejected_gate_traces_back_to_the_risk_behind_it():
    trace = run_scenario("go_nogo_decision")
    gate = next(p for p in hitl.list_pending() if p["payload"]["schema"] == "gate_review.v1"
                and p["message_id"] in {c["message_id"] for c in trace["commit"]})
    done = hitl.resolve(gate["approval_id"], approver="pm@demo", decision="reject",
                        rationale="open risk")
    doc = _prov(done["decision_record"])
    _closed(doc)
    dec = f"dec:{done['decision_record']}"
    assert doc["entity"][dec]["mapmo:justification"] == "open risk"
    used = {b["prov:usedEntity"] for b in doc["wasDerivedFrom"].values()
            if b["prov:generatedEntity"] == dec}
    assert f"msg:{gate['message_id']}" in used and len(used) > 1  # the decision and its reviews
    people = [a for a, v in doc["agent"].items() if v["prov:type"] == "prov:Person"]
    assert people == ["person:pm%40demo"]
    (approval,) = [a for a in doc["activity"] if a.startswith("approval:")]
    assert {"prov:entity": dec, "prov:activity": approval} in doc["wasGeneratedBy"].values()
    steps = [a for a in doc["activity"] if a.startswith("step:")]
    assert len(steps) == 4  # A4, A6, A5, A8
    informed = list(doc["wasInformedBy"].values())
    assert len(informed) == len(steps)  # a chain of steps, then the approval
    # the review's evidence: an A4 risk message, attributed to A4
    derived = {(b["prov:generatedEntity"], b["prov:usedEntity"])
               for b in doc["wasDerivedFrom"].values()}
    sources = {u for g, u in derived if g != dec}
    assert any({"prov:entity": s, "prov:agent": "agent:A4"} in doc["wasAttributedTo"].values()
               for s in sources)


def test_a_direct_decision_has_its_own_activity():
    budgets.set_budget(budgets.MONTH, 1.0, 2.0, by="finance")
    rec = client.get("/decisions", params={"kind": "budget"}).json()[0]
    doc = _prov(rec["id"])
    _closed(doc)
    (act,) = doc["activity"]
    assert act.endswith(".decide") and doc["activity"][act]["prov:type"] == "mapmo:Decide"
    assert list(doc["agent"]) == ["person:finance"]
    budgets.set_budget(budgets.MONTH, None, None, by="finance")
    assert client.get("/decisions/DEC-missing/provenance").status_code == 404


def test_the_export_reads_with_the_prov_library():
    prov = pytest.importorskip("prov.model")  # optional: not a dependency of MA-PMO
    run_scenario("go_nogo_decision")
    for rec in client.get("/decisions", params={"limit": 5}).json():
        parsed = prov.ProvDocument.deserialize(content=json.dumps(_prov(rec["id"])),
                                               format="json")
        assert parsed.get_records()
