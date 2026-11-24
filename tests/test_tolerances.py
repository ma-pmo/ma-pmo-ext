"""Roadmap 10, step 2: tolerances, and exceptions raised before they are broken."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

from ma_pmo.api.auth import required_role
from ma_pmo.api.main import app
from ma_pmo.core import guardrails, hitl, policy, tolerances
from ma_pmo.core.config import get_settings
from ma_pmo.core.scenarios import run_scenario
from ma_pmo.core.scope import DEFAULT_SCOPE
from ma_pmo.db.models import Policy
from ma_pmo.db.session import get_session

client = TestClient(app)


@pytest.fixture(autouse=True)
def _demo_week(monkeypatch):
    monkeypatch.setattr(get_settings(), "report_as_of", "2026-02-16")
    yield
    with get_session() as s:
        s.execute(delete(Policy))


def test_a_lower_level_can_only_narrow():
    tolerances.validate({"workspace": {"max_slip_days": 10},
                         "portfolios": {DEFAULT_SCOPE: {"max_slip_days": 5}},
                         "projects": {"PROJ-31": {"max_slip_days": 2}}})
    with pytest.raises(ValueError, match="only narrow"):
        tolerances.validate({"workspace": {"max_slip_days": 5},
                             "projects": {"PROJ-31": {"max_slip_days": 9}}})
    with pytest.raises(ValueError, match="only narrow"):
        tolerances.validate({"workspace": {"min_spi": 0.9},
                             "portfolios": {DEFAULT_SCOPE: {"min_spi": 0.8}}})
    with pytest.raises(ValueError, match="unknown tolerance"):
        tolerances.validate({"workspace": {"max_budget": 1}})
    with pytest.raises(ValueError, match="max_severity"):
        tolerances.validate({"workspace": {"max_severity": "huge"}})


def test_the_tightest_limit_is_in_force():
    doc = {"workspace": {"max_slip_days": 10, "max_severity": "high"},
           "portfolios": {DEFAULT_SCOPE: {"max_slip_days": 5}},
           "projects": {"PROJ-31": {"max_severity": "medium"}}}
    found = tolerances.effective("PROJ-31", DEFAULT_SCOPE, doc)
    assert found["max_slip_days"] == {"value": 5, "level": f"portfolio {DEFAULT_SCOPE}"}
    assert found["max_severity"] == {"value": "medium", "level": "project PROJ-31"}
    assert tolerances.effective("PROJ-14", None, doc)["max_slip_days"]["value"] == 10


def test_each_measured_dimension_finds_its_breach():
    doc = {"workspace": {"max_slip_days": 0, "min_spi": 1.0, "max_severity": "medium",
                         "max_unstaffed_pct": 1}}
    late = tolerances._breaches("schedule.v1", {"project_id": "PROJ-31",
                                                "forecast_finish": "2026-04-30"},
                                DEFAULT_SCOPE, doc)
    assert {b["dimension"] for b in late} == {"time", "quality"}  # PROJ-31's SPI is 0.994
    assert next(b for b in late if b["dimension"] == "time")["forecast"] > 0
    risky = tolerances._breaches("risk_alert.v1", {"project_id": "PROJ-31", "severity": "high"},
                                 DEFAULT_SCOPE, doc)
    assert risky[0]["dimension"] == "risk" and risky[0]["tolerance"] == "medium"
    short = tolerances._breaches("allocation.v1", {"unstaffed": [{
        "project_id": "PROJ-14", "skill": "ml", "remaining_hours": 40, "reason": "no_skill"}]},
        DEFAULT_SCOPE, doc)
    assert short[0]["dimension"] == "scope" and short[0]["forecast"] > 1


def test_observe_records_and_enforce_raises_an_exception():
    policy.change({}, by="pmo", tolerances={"workspace": {"max_severity": "medium"}})
    ours = {m["message_id"] for m in run_scenario("risk_escalation")["communications"]}
    asked = [e for e in guardrails.log(name="tolerance", outcome="ask", limit=50)
             if e["message_id"] in ours]
    assert asked and all((e["mode"], e["decision"]) == ("observe", "allow") for e in asked)
    assert not [p for p in hitl.list_pending() if p["message_id"] in ours and p["exception"]]
    policy.change({"tolerance": {"mode": "enforce"}}, by="pmo")
    ours = {m["message_id"] for m in run_scenario("risk_escalation")["communications"]}
    raised = [p for p in hitl.list_pending() if p["message_id"] in ours and p["exception"]]
    assert raised
    breach = raised[0]["exception"]["breaches"][0]
    assert (breach["dimension"], breach["tolerance"], breach["level"]) == (
        "risk", "medium", "workspace")


def test_the_api_sets_and_shows_tolerances_with_admin():
    assert required_role("PUT", "/tolerances") == "admin"
    body = {"tolerances": {"workspace": {"max_slip_days": 5},
                           "projects": {"PROJ-31": {"max_slip_days": 2}}}, "note": "q1"}
    assert client.put("/tolerances", json=body).json()["tolerances"]["projects"] == {
        "PROJ-31": {"max_slip_days": 2}}
    got = client.get("/tolerances", params={"project": "PROJ-31"}).json()
    assert got["effective"]["max_slip_days"] == {"value": 2, "level": "project PROJ-31"}
    wider = {"tolerances": {"workspace": {"max_slip_days": 1},
                            "projects": {"PROJ-31": {"max_slip_days": 3}}}}
    assert client.put("/tolerances", json=wider).status_code == 400
