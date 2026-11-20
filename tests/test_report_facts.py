"""Roadmap 12, step 1: the facts under A5's report, report kinds, and reading reports back."""
from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from ma_pmo.agents.reporting import ReportingAgent
from ma_pmo.cli import main as cli
from ma_pmo.core.config import get_settings
from ma_pmo.core.schemas.payloads import PAYLOAD_REGISTRY
from ma_pmo.core.schemas.payloads.report_v2 import ReportV2
from ma_pmo.db.models import Report
from ma_pmo.db.session import get_session
from ma_pmo.reports import facts, kinds, render, store

TODAY = date(2026, 2, 1)
SCOPE = "PORTFOLIO#2026-Q1"


def task(tid, effort, pct, deps=()):
    return {"task_id": tid, "wbs": tid, "effort": effort, "percent_complete": pct,
            "deps": list(deps)}


def portfolio(*projects):
    return {"portfolio_id": "P", "found": True, "projects": list(projects)}


# planned 2026-01-01 → 2026-03-02 (60 days); on 2026-02-01 (31 days in) PV is 31/60 of the work
AHEAD = {"project_id": "A", "status": "green", "percent_complete": 62.0,
         "planned_start": "2026-01-01", "planned_finish": "2026-03-02", "deadline": "2026-03-31",
         "tasks": [task("A1", 50, 100), task("A2", 50, 24, ["A1"])]}
BEHIND = {"project_id": "B", "status": "amber", "percent_complete": 25.0,
          "planned_start": "2026-01-01", "planned_finish": "2026-03-02", "deadline": "2026-03-10",
          "tasks": [task("B1", 100, 25)]}
NOT_STARTED = {"project_id": "C", "status": "green", "percent_complete": 0.0,
               "planned_start": "2026-03-01", "planned_finish": "2026-04-01",
               "deadline": "2026-04-30", "tasks": [task("C1", 10, 0)]}


def by_id(items):
    return {x.id: x for x in items}


def test_spi_and_forecast_follow_the_plan_baseline():
    f = facts.build(portfolio(AHEAD, BEHIND, NOT_STARTED), today=TODAY)
    p = {x.project_id: x for x in f.projects}
    share = 31 / 60
    assert p["A"].spi == round(0.62 / share, 3)  # ahead
    assert p["B"].spi == round(0.25 / share, 3)  # behind
    assert p["C"].spi is None and p["C"].forecast_finish == "2026-04-01"  # the plan, unchanged
    # forecast = start + planned duration / SPI
    assert p["B"].forecast_finish == "2026-05-05" and p["B"].slack_days == -56  # 60/0.484 d
    assert p["A"].slack_days > 0
    k = by_id(f.kpis)
    assert k["kpi.spi"].value == round((62 + 25) / (200 * share), 3)
    assert (k["kpi.late"].value, k["kpi.worst_slack"].value) == (1, -56)
    assert f.as_of == "2026-02-01" and f.previous_report_id is None
    assert all(x.previous is None and x.delta is None for x in f.kpis)


def test_a_finished_project_has_no_forecast():
    done = {**AHEAD, "percent_complete": 100.0, "tasks": [task("A1", 100, 100)]}
    [p] = facts.build(portfolio(done), today=TODAY).projects
    assert p.forecast_finish is None and p.slack_days is None


def test_tolerances_and_overall_status(monkeypatch):
    f = facts.build(portfolio(AHEAD, BEHIND), today=TODAY)
    assert {(t.project_id, t.dimension) for t in f.breaches} == {("B", "schedule"), ("B", "spi")}
    assert facts.overall_status(f) == "amber"
    green_behind = {**BEHIND, "status": "green"}
    assert facts.overall_status(facts.build(portfolio(green_behind), today=TODAY)) == "amber"
    red = {**AHEAD, "status": "red"}
    assert facts.overall_status(facts.build(portfolio(red), today=TODAY)) == "red"
    monkeypatch.setattr(get_settings(), "tolerance_spi", 0.1)
    monkeypatch.setattr(get_settings(), "tolerance_slip_days", 365)
    relaxed = facts.build(portfolio(AHEAD, green_behind), today=TODAY)
    assert relaxed.breaches == [] and facts.overall_status(relaxed) == "green"


def test_the_as_of_date_comes_from_the_step_or_the_setting(monkeypatch):
    assert facts.as_of_date("2026-01-15") == date(2026, 1, 15)
    monkeypatch.setattr(get_settings(), "report_as_of", "2026-02-20")
    assert facts.as_of_date() == date(2026, 2, 20)


def test_a_project_report_keeps_only_its_projects():
    board = [{"schema": "risk_alert.v1", "message_id": "m1",
              "data": {"project_id": "A", "severity": "high", "signal": "s", "mitigation": "x"}},
             {"schema": "risk_alert.v1", "message_id": "m2",
              "data": {"project_id": "B", "severity": "low", "signal": "s", "mitigation": "x"}}]
    f = facts.build(portfolio(AHEAD, BEHIND), today=TODAY, projects=["A"], board=board)
    assert [p.project_id for p in f.projects] == ["A"] and f.projects_in_scope == ["A"]
    assert [r.message_id for r in f.risks] == ["m1"] and f.board_read


def test_compared_with_the_previous_report():
    first = facts.build(portfolio(AHEAD, BEHIND), today=TODAY)
    stored = ReportV2(scope="P", path="rule", overall_status="amber", facts=first,
                      executive_summary="x", project_status=[]).model_dump()
    for p in stored["facts"]["projects"]:
        if p["project_id"] == "B":
            p.update(status="green", percent_complete=5.0)
    moved = {**BEHIND, "status": "red", "percent_complete": 35.0}
    f = facts.build(portfolio(AHEAD, moved), ("RPT-1", "2026-01-25", stored), today=TODAY)
    assert (f.previous_report_id, f.period_start) == ("RPT-1", "2026-01-25")
    k = by_id(f.kpis)
    assert (k["kpi.red"].previous, k["kpi.red"].value, k["kpi.red"].delta) == (0, 1, 1)
    assert k["kpi.progress"].delta == 5.0
    b = next(p for p in f.projects if p.project_id == "B")
    assert (b.previous_status, b.previous_percent_complete) == ("green", 5.0)


def test_a_report_v1_row_still_reads_as_a_report():
    v1 = {"scope": "P", "executive_summary": "x", "key_risks": [], "recommended_actions": [],
          "project_status": [{"project_id": "A", "name": "A", "status": "amber",
                              "percent_complete": 40.0, "headline": ""}]}
    f = facts.build(portfolio(AHEAD), ("RPT-0", "2026-01-01", v1), today=TODAY)
    assert f.projects[0].previous_status == "amber"
    upgraded = store.as_v2(v1, "2026-01-01T09:00:00")
    assert upgraded["kind"] == "status" and upgraded["overall_status"] == "amber"
    assert "x" in render.render(upgraded, "RPT-0", "md")
    assert store.as_v2({"note": "not a report"}, "2026-01-01") is None


@pytest.mark.parametrize("kind", sorted(kinds.KINDS))
def test_each_kind_has_its_own_narrative_and_sections(kind):
    board = [{"schema": "gate_review.v1", "message_id": "g1",
              "data": {"project_id": "B", "gate": "G3-execution", "decision": "fail",
                       "checklist": [{"criterion": "SPI ≥ 0.8", "passed": False}],
                       "conditions": []}},
             {"schema": "knowledge.v1", "message_id": "k1",
              "data": {"query": "q", "answer": "a",
                       "citations": [{"source_id": "LL-1", "excerpt": "lesson"}]}}]
    f = facts.build(portfolio(AHEAD, BEHIND), today=TODAY, board=board)
    from ma_pmo.agents.reporting import _fallback_report

    text = kinds.narrate(kind, _fallback_report(portfolio(AHEAD, BEHIND), "P"), f)
    report = ReportV2(scope="P", kind=kind, title=kinds.title(kind), path="rule",
                      overall_status=facts.overall_status(f), facts=f,
                      **text.model_dump(exclude={"scope"}))
    md = render.to_markdown(report, "RPT-x")
    headings = [line[3:] for line in md.splitlines() if line.startswith("## ")]
    assert len(headings) == len(kinds.spec(kind).sections)
    assert "Outside tolerance: B" in text.executive_summary
    if kind in ("gate", "closure"):
        assert "1 fail" in text.executive_summary
        assert any("G3-execution" in a for a in text.recommended_actions)
    if kind == "closure":
        assert "LL-1: lesson" in md
    if kind in ("exception", "executive"):
        assert text.recommended_actions[0].startswith("Decide recovery for B")


def test_formats(tmp_path):
    f = facts.build(portfolio(AHEAD, BEHIND), today=TODAY)
    content = ReportV2(scope="P", kind="status", path="rule", overall_status="amber",
                       facts=f, executive_summary="Two <projects>", project_status=[]
                       ).model_dump()
    html = render.render(content, "RPT-1", "html")
    assert html.startswith("<!doctype html>") and "Two &lt;projects&gt;" in html
    csv_rows = render.render(content, "RPT-1", "csv").strip().splitlines()
    assert len(csv_rows) == 3 and csv_rows[2].startswith("RPT-1,status,P,2026-02-01,B,amber")
    assert '"id": "RPT-1"' in render.render(content, "RPT-1", "json")
    with pytest.raises(ValueError):
        render.render(content, "RPT-1", "pdf")
    ko = render.render({**content, "language": "ko"}, "RPT-1", "md")
    assert "## 핵심 지표" in ko


def _run(kind="status", **params):
    return ReportingAgent().run({"goal": "report", "task_ref": SCOPE, "kind": kind,
                                 "as_of": "2026-02-16", **params})


def test_a5_stores_report_v2_and_compares_with_its_last_report_of_the_same_kind():
    assert PAYLOAD_REGISTRY["report.v2"] is ReportV2
    first, second = _run(), _run()
    _run("exception")  # another kind does not become the status report's previous report
    third = _run()
    assert third["outputs"][0]["schema"] == "report.v1"  # what other agents read is unchanged
    assert first["outputs"][0]["data"] == second["outputs"][0]["data"]
    with get_session() as s:
        rows = s.scalars(select(Report).where(Report.scope == SCOPE)
                         .order_by(Report.created_at.desc())).all()
    latest = ReportV2.model_validate(rows[0].content)
    assert latest.kind == "status" and latest.path == "rule" and latest.audience == "team"
    assert latest.facts.previous_report_id == rows[2].id  # skips the exception report
    assert all(k.previous == k.value for k in latest.facts.kpis)
    assert latest.to_v1().model_dump() == third["outputs"][0]["data"]


def test_a_project_report_from_a_step(monkeypatch):
    out = _run("executive", projects=["PROJ-31"], audience="team")
    rid, content = store.latest(SCOPE, "executive")
    assert content["facts"]["projects_in_scope"] == ["PROJ-31"]
    assert [p["project_id"] for p in content["facts"]["projects"]] == ["PROJ-31"]
    assert content["audience"] == "team"
    assert [p["project_id"] for p in out["outputs"][0]["data"]["project_status"]] == ["PROJ-31"]


def test_the_api_lists_shows_and_exports_reports():
    from ma_pmo.api.main import app

    _run("gate")
    client = TestClient(app)
    listed = client.get("/reports", params={"kind": "gate"}).json()
    assert listed and listed[0]["kind"] == "gate"
    rid = listed[0]["id"]
    assert client.get(f"/reports/{rid}").json()["facts"]["as_of"] == "2026-02-16"
    assert client.get("/reports/latest", params={"kind": "gate"}).json()["id"] == rid
    r = client.get(f"/reports/{rid}/export", params={"format": "md"})
    assert r.status_code == 200 and r.text.startswith("# Gate decision pack")
    assert "attachment" in r.headers["content-disposition"]
    assert rid in r.headers["content-disposition"]
    inline = client.get(f"/reports/{rid}/export", params={"format": "html", "inline": True})
    assert inline.headers["content-disposition"].startswith("inline")
    assert client.get(f"/reports/{rid}/export", params={"format": "pdf"}).status_code == 400
    assert client.get("/reports/RPT-nope").status_code == 404


def test_the_cli_lists_shows_and_exports(tmp_path, capsys):
    _run("closure")
    assert cli(["report", "list", "--kind", "closure"]) == 0
    assert "closure" in capsys.readouterr().out
    assert cli(["report", "show", "latest", "--kind", "closure"]) == 0
    assert capsys.readouterr().out.startswith("# Closure report")
    out = tmp_path / "r.html"
    assert cli(["report", "export", "latest", "--kind", "closure", "--out", str(out)]) == 0
    assert out.read_text(encoding="utf-8").startswith("<!doctype html>")
    assert cli(["report", "show", "RPT-nope"]) == 1
