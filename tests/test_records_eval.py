"""Roadmap 8, step 6: the record-completeness evaluation measures what it says, on a few runs."""
from __future__ import annotations

from ma_pmo.core import scenarios as catalog
from ma_pmo.eval import records, review


def test_scenarios_leave_complete_records(monkeypatch):
    monkeypatch.setattr(catalog, "SCENARIOS",
                        {k: catalog.SCENARIOS[k] for k in ("go_nogo_decision", "risk_escalation")})
    rows = records.scenarios()
    assert [r["name"] for r in rows] == ["go_nogo_decision", "risk_escalation"]
    share = records.summary(rows)
    for key in records.TARGETS:
        assert share[key] in (1.0, None), (key, share[key])
    total = records._sum(rows)
    assert total["agent_decisions"] and total["person_decisions"] and total["reason_needed"]
    assert total["sent"] and total["failed"]  # the stand-in notifiers were really told


def test_review_cases_keep_the_reason_for_overrides(monkeypatch):
    picked = [c for c in review.cases() if c.gate][:2]
    monkeypatch.setattr(review, "cases", lambda: picked)
    rows = records.review_cases()
    share = records.summary(rows)
    for key in records.TARGETS:
        assert share[key] in (1.0, None), (key, share[key])
    assert records._sum(rows)["refused"] >= 1  # a reason was asked for and enforced
    assert "| reason where required | 100% |" in records.to_markdown(
        {"scenarios": {"rows": rows, "total": records._sum(rows), "share": share},
         "review_cases": {"rows": rows, "total": records._sum(rows), "share": share}})
