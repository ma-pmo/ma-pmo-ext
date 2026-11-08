"""Alternatives: every challenged decision reaches a person with another course next to it."""
from __future__ import annotations

import pytest

from ma_pmo.agents import cross_checks
from ma_pmo.core import commit
from ma_pmo.core.config import get_settings
from tests.spike import VARIANTS, portfolio, reviews, run_full, spec

PLAIN = [
    {"id": "A3", "agent": "A3"},
    {"id": "A4", "agent": "A4", "needs": []},
    {"id": "A6", "agent": "A6", "needs": ["A3", "A4"], "params": {"gate": "G3-execution"}},
    {"id": "A5", "agent": "A5", "needs": ["A6"]},
]
# the challenged constraint -> the kinds of alternative offered for it
OFFERED = {"gate.no_open_high_risk": {"conditional_on_mitigation"},
           "gate.staffed": {"add_capacity"},
           "gate.allocation_by_deadline": {"move_deadline", "add_capacity"}}


@pytest.fixture(autouse=True)
def alternatives_on(monkeypatch):
    """Alternatives are opt-in (MA_PMO_REVIEW_ALTERNATIVES); these tests turn them on."""
    monkeypatch.setattr(get_settings(), "review_alternatives", True)


def _held(result: dict) -> dict:
    gate = next(c for c in result["commit"]
                if c["schema"] == "gate_review.v1" and c["project_id"] == "PROJ-X")
    return next(p for p in result["pending"] if p["message_id"] == gate["message_id"])


@pytest.mark.parametrize("name", sorted(n for n, v in VARIANTS.items() if v[1]))
def test_each_challenge_comes_with_its_alternatives(name, monkeypatch):
    expected = VARIANTS[name][1]
    item = _held(run_full(monkeypatch, portfolio(name), spec(PLAIN, review=True)))
    offered = {a["alternative"]["kind"] for a in item["review"]["alternatives"]}
    assert offered == set().union(*(OFFERED[c] for c in expected))
    assert "alternative" not in item["review"]["missing"]
    for a in item["review"]["alternatives"]:
        assert a["agent"] == "A8" and a["evidence"] and a["alternative"]["summary"]
        assert a["alternative"]["decision"] == "conditional"


def test_no_alternatives_without_a_challenge(monkeypatch):
    for name in ("control_healthy", "control_done"):
        result = run_full(monkeypatch, portfolio(name), spec(PLAIN, review=True))
        assert [r for r in reviews(result["outputs"]) if r["verdict"] == "ALTERNATIVE"
                and r.get("project_id") == "PROJ-X"] == []


def test_the_numbers_follow_the_plan(monkeypatch):
    result = run_full(monkeypatch, portfolio("alloc_after_deadline"), spec(PLAIN, review=True))
    plan = next(o["data"] for o in result["outputs"] if o["schema"] == "allocation.v1")["plan"]
    mine = [ln for ln in plan if ln["project_id"] == "PROJ-X"]
    by_kind = {a["alternative"]["kind"]: a["alternative"]
               for a in _held(result)["review"]["alternatives"]}
    assert by_kind["move_deadline"]["new_deadline_week"] == max(ln["week"] for ln in mine)
    late = sum(ln["hours"] for ln in mine if ln["week"] > "2026-W05")  # deadline 2026-01-30
    weeks = 3  # 2026-W03 (plan start) through 2026-W05
    assert by_kind["add_capacity"]["hours_per_week"] == round(late / weeks, 1)
    assert by_kind["add_capacity"]["until"] == "2026-W05"
    risky = _held(run_full(monkeypatch, portfolio("red_but_on_spi"), spec(PLAIN, review=True)))
    [cond] = risky["review"]["alternatives"]
    alert = next(o["data"] for o in run_full(monkeypatch, portfolio("red_but_on_spi"),
                                             spec(PLAIN, review=True))["outputs"]
                 if o["schema"] == "risk_alert.v1" and o["data"]["project_id"] == "PROJ-X")
    assert cond["alternative"]["condition"] == alert["mitigation"]
    unstaffed = _held(run_full(monkeypatch, portfolio("no_skill"), spec(PLAIN, review=True)))
    [add] = unstaffed["review"]["alternatives"]
    assert add["alternative"]["skill"] == "ml" and add["alternative"]["hours_per_week"] > 0


def test_alternatives_are_off_by_default(monkeypatch):
    monkeypatch.setattr(get_settings(), "review_alternatives", False)
    item = _held(run_full(monkeypatch, portfolio("red_but_on_spi"), spec(PLAIN, review=True)))
    assert item["review"]["alternatives"] == [] and item["review"]["missing"] == []


def test_a_challenge_without_an_alternative_is_reported(monkeypatch):
    monkeypatch.setattr(cross_checks, "alternatives", lambda *a, **k: [])
    result = run_full(monkeypatch, portfolio("red_but_on_spi"), spec(PLAIN, review=True))
    item = _held(result)
    assert item["review"]["alternatives"] == [] and "alternative" in item["review"]["missing"]
    gate = next(c for c in result["commit"] if c["message_id"] == item["message_id"])
    assert gate["status"] == commit.REVIEW_PENDING and gate["missing"] == ["alternative"]
