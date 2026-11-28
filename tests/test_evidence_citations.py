"""Gate, report, risk and allocation decisions cite what they rest on (records evaluation)."""
from __future__ import annotations

import pytest
from sqlalchemy import select

from ma_pmo.core.config import get_settings
from ma_pmo.core.scenarios import run_scenario
from ma_pmo.db.models import AgentMessageRow
from ma_pmo.db.session import get_session


@pytest.fixture(autouse=True)
def _demo_week(monkeypatch):
    monkeypatch.setattr(get_settings(), "report_as_of", "2026-02-16")


def _cited(run_id: str, schema: str) -> list[list[dict]]:
    with get_session() as s:
        rows = s.scalars(select(AgentMessageRow).where(AgentMessageRow.run_id == run_id)).all()
        return [r.evidence or [] for r in rows if (r.payload or {}).get("schema") == schema]


def test_each_decision_cites_the_tracker_fields_or_messages_it_used():
    run = run_scenario("executive_briefing")["run_id"]
    for schema in ("risk_alert.v1", "allocation.v1"):
        cited = _cited(run, schema)
        assert cited and all(any(e["kind"] == "tracker" for e in ev) for ev in cited), schema
    (report,) = _cited(run, "report.v1")
    with get_session() as s:
        ours = set(s.scalars(select(AgentMessageRow.message_id)
                             .where(AgentMessageRow.run_id == run)))
    assert {e["ref"] for e in report if e["kind"] == "message"} & ours  # the risks it summarises
    assert any(e["kind"] == "tracker" and e.get("field") == "deadline" for e in report)
    gates = _cited(run_scenario("go_nogo_decision")["run_id"], "gate_review.v1")
    assert gates and all("tasks" in {e.get("field") for e in ev} for ev in gates)
