"""Commit gate: a reviewed run commits only decisions its reviews hold up; the rest go to a person.

The completion test of the 0.6.0 spike: every conflict it found must now reach a person with
both sides in view (held and linked), and its controls must not add to anyone's queue.
"""
from __future__ import annotations

from collections import Counter

import pytest
from sqlalchemy import func, select

from ma_pmo.core import commit, hitl, runs, scenarios
from ma_pmo.db.models import Approval
from ma_pmo.db.session import get_session
from tests.spike import VARIANTS, portfolio, run_full, spec

PLAIN = [
    {"id": "A3", "agent": "A3"},
    {"id": "A4", "agent": "A4", "needs": []},
    {"id": "A6", "agent": "A6", "needs": ["A3", "A4"], "params": {"gate": "G3-execution"}},
    {"id": "A5", "agent": "A5", "needs": ["A6"]},
]


def _gate(result: dict, project: str) -> dict:
    return next(c for c in result["commit"]
                if c["schema"] == "gate_review.v1" and c["project_id"] == project)


def _held_item(result: dict, message_id: str) -> dict | None:
    return next((p for p in result["pending"] if p["message_id"] == message_id), None)


@pytest.mark.parametrize("name", sorted(VARIANTS))
def test_every_spike_conflict_reaches_a_person_with_both_sides(name, monkeypatch):
    _change, expected, _fixed = VARIANTS[name]
    result = run_full(monkeypatch, portfolio(name), spec(PLAIN, review=True))
    gate = _gate(result, "PROJ-X")
    item = _held_item(result, gate["message_id"])
    if not expected:  # no conflict: committed, and review asks nobody anything
        assert gate["status"] == commit.COMMITTED and gate["challenges"] == []
        # a gate that fails on its own criteria (stalled_green) is still queued by A6 itself
        assert item is None or (item["review"] is None and item["intent"] == "propose")
        return
    assert gate["status"] == commit.REVIEW_PENDING  # held
    assert item is not None and item["review"]["kind"] == "review_pending"
    challenged = Counter(c["constraint"] for c in item["review"]["challenges"])
    assert set(challenged) == expected
    assert all(n == 2 for n in challenged.values())  # the builder and the dedicated reviewer
    for c in item["review"]["challenges"]:  # linked: the other side, with its evidence
        assert c["verdict"] == "CHALLENGE" and c["rationale"] and c["evidence"]
    assert item["review"]["missing"] == []  # challenged is not the same as unchecked
    report = next(c for c in result["commit"] if c["schema"] == "report.v1")
    assert report["status"] == commit.COMMITTED  # A5 already added what was missing


def test_the_spike_totals(monkeypatch):
    """11 conflicts: 9 on gates, all held and linked; 2 in reports, fixed in the report itself."""
    gate_conflicts = held = 0
    report_fixes = 0
    for name, (_change, expected, fixed) in VARIANTS.items():
        result = run_full(monkeypatch, portfolio(name), spec(PLAIN, review=True))
        gate = _gate(result, "PROJ-X")
        gate_conflicts += len(expected)
        if expected and _held_item(result, gate["message_id"]):
            held += len({c["constraint"] for c in
                         _held_item(result, gate["message_id"])["review"]["challenges"]})
        report = next(o["data"] for o in result["outputs"] if o["schema"] == "report.v1")
        report_fixes += fixed and any(k.startswith("PROJ-X") for k in report["key_risks"])
    assert (gate_conflicts, held, report_fixes) == (9, 9, 2)


def test_a_decision_already_queued_keeps_one_approval(monkeypatch):
    result = run_full(monkeypatch, portfolio("control_healthy"), spec(PLAIN, review=True))
    # PROJ-31 is red with a failing gate: queued by A6 itself, and challenged on risk
    gate = _gate(result, "PROJ-31")
    assert gate["status"] == commit.REVIEW_PENDING
    items = [p for p in result["pending"] if p["message_id"] == gate["message_id"]]
    assert len(items) == 1 and items[0]["review"]["challenges"]
    assert _gate(result, "PROJ-22")["status"] == commit.COMMITTED


def test_checking_again_adds_nothing(monkeypatch):
    result = run_full(monkeypatch, portfolio("red_but_on_spi"), spec(PLAIN, review=True))
    held = [c["message_id"] for c in result["commit"] if c["status"] == commit.REVIEW_PENDING]
    assert held and len(result["pending"]) == len({p["message_id"] for p in result["pending"]})


def test_without_a_dedicated_reviewer_nothing_commits(monkeypatch):
    """A run that never had A8 cannot commit anything: every decision goes to a person."""
    result = run_full(monkeypatch, portfolio("control_healthy"), spec(PLAIN), gate=True)
    assert result["commit"] and {c["status"] for c in result["commit"]} == {commit.REVIEW_PENDING}
    assert {tuple(c["missing"]) for c in result["commit"]} == {("review.dedicated",)}
    queued = {p["message_id"] for p in result["pending"]}
    assert {c["message_id"] for c in result["commit"]} <= queued


def test_a_constraint_nobody_could_check_holds_the_decision(monkeypatch):
    """Without a deadline the allocation check cannot run: not checked is not verified."""
    status = portfolio("control_healthy")
    next(p for p in status["projects"] if p["project_id"] == "PROJ-X")["deadline"] = None
    result = run_full(monkeypatch, status, spec(PLAIN, review=True))
    gate = _gate(result, "PROJ-X")
    assert gate["status"] == commit.REVIEW_PENDING and gate["challenges"] == []
    assert gate["missing"] == ["gate.allocation_by_deadline"]
    assert _held_item(result, gate["message_id"])["review"]["missing"] == gate["missing"]


def test_an_unreviewed_run_is_not_gated():
    trace = scenarios.run_scenario("risk_escalation")
    assert trace["commit"] is None
    with get_session() as s:
        assert s.scalar(select(func.count()).select_from(Approval).where(
            Approval.run_id == trace["run_id"], Approval.reason.is_not(None))) == 0


def test_a_reviewed_scenario_on_the_demo_data():
    flow = scenarios.loaded("risk_escalation").model_copy(update={"review": True})
    trace = scenarios.run_spec(flow)
    assert trace["status"] == "succeeded"
    by_project = {c["project_id"]: c for c in trace["commit"] if c["schema"] == "gate_review.v1"}
    assert by_project["PROJ-31"]["status"] == commit.REVIEW_PENDING  # rated high by A4
    assert runs.get_state(trace["run_id"])["commit"] == trace["commit"]
    pending = {p["message_id"]: p for p in hitl.list_pending()}
    held = pending[by_project["PROJ-31"]["message_id"]]
    assert {c["constraint"] for c in held["review"]["challenges"]} == {"gate.no_open_high_risk"}
    # resolving it is an ordinary approval; the finished run stays finished
    done = hitl.resolve(held["approval_id"], approver="pm", decision="approve")
    assert done["decision"] == "approve" and runs.get_run(trace["run_id"])["status"] == \
        "succeeded"
