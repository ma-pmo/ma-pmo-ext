"""Roadmap 10, step 5: the evidence pack for a period."""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

from ma_pmo.api.main import app
from ma_pmo.core import evidence, hitl, policy
from ma_pmo.core.config import get_settings
from ma_pmo.core.scenarios import run_scenario
from ma_pmo.db.models import Policy
from ma_pmo.db.session import get_session

client = TestClient(app)


@pytest.fixture(autouse=True)
def _demo_week(monkeypatch):
    monkeypatch.setattr(get_settings(), "report_as_of", "2026-02-16")
    yield
    with get_session() as s:
        s.execute(delete(Policy))


def test_the_pack_holds_policy_checks_exceptions_and_approvals():
    policy.change({}, by="pmo", note="Q1 limits",
                  tolerances={"projects": {"PROJ-31": {"max_slip_days": 0}}})
    policy.change({"tolerance": {"mode": "enforce"}}, by="pmo", note="exceptions on")
    ours = {m["message_id"] for m in run_scenario("schedule_recovery")["communications"]}
    raised = next(p for p in hitl.list_pending() if p["message_id"] in ours and p["exception"])
    hitl.resolve(raised["approval_id"], approver="sponsor", decision="approve",
                 rationale="accepted for Q1")
    pack = evidence.build(date.today() - timedelta(days=1), date.today())
    assert [v["note"] for v in pack["policy_versions"]] == ["Q1 limits", "exceptions on"]
    assert pack["policy_in_force"]["guardrails"]["tolerance"] == "enforce"
    assert any(c["guardrail"] == "tolerance" and c["outcome"] == "ask" for c in
               pack["guardrail_counts"])
    (exc,) = [e for e in pack["exceptions"] if e["approval_id"] == raised["approval_id"]]
    assert exc["approver"] == "sponsor" and exc["breaches"][0]["project"] == "PROJ-31"
    assert any(a["rationale"] == "accepted for Q1" for a in pack["approvals"])
    names = {m.get("guardrail") for m in pack["mapping"]}
    assert {"schema", "budget", "tolerance", "segregation"} <= names
    assert "does not claim conformity" in pack["disclaimer"]


def test_the_api_returns_json_or_a_markdown_file():
    as_json = client.get("/evidence").json()
    assert set(as_json) >= {"policy_versions", "guardrail_counts", "exceptions", "mapping"}
    md = client.get("/evidence", params={"format": "md", "since": "2026-01-01"})
    assert md.headers["content-type"].startswith("text/markdown")
    assert "attachment" in md.headers["content-disposition"]
    assert md.text.startswith("# Evidence pack") and "does not claim conformity" in md.text
