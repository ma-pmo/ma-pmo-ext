"""Roadmap 12, step 2: insights across reports, and checking the LLM's narrative against facts."""
from __future__ import annotations

from datetime import date

from ma_pmo.agents.reporting import ReportingAgent
from ma_pmo.core.schemas.payloads.report_v1 import ProjectStatusLine, ReportV1
from ma_pmo.core.schemas.payloads.report_v2 import ReportV2
from ma_pmo.reports import facts, grounding, insights, render, store

SCOPE = "PORTFOLIO#2026-Q1"


def task(tid, effort, pct):
    return {"task_id": tid, "wbs": tid, "effort": effort, "percent_complete": pct, "deps": []}


def project(pid="A", status="green", pct=50.0, deadline="2026-03-31"):
    return {"project_id": pid, "status": status, "percent_complete": pct,
            "planned_start": "2026-01-01", "planned_finish": "2026-03-02", "deadline": deadline,
            "tasks": [task(f"{pid}1", 100, pct)]}


def stored(f, *, kind="status"):
    """`f` as a stored report, as `earlier_reports` returns it."""
    content = ReportV2(scope="P", kind=kind, path="rule", overall_status="green", facts=f,
                       executive_summary="x", project_status=[]).model_dump()
    return ("RPT-prev", f.as_of, content)


def at(day, *projects, board=None):
    steps = None if board is None else [{"step": "A4", "agent": "A4"}]
    return facts.build({"portfolio_id": "P", "projects": list(projects)},
                       today=date.fromisoformat(day), board=board, steps=steps)


def kinds_of(found):
    return [(i.kind, i.project_id) for i in found]


def test_the_first_report_has_nothing_to_compare():
    assert insights.build(at("2026-02-01", project()), []) == []


def test_status_tolerance_and_forecast_changes():
    before = at("2026-02-01", project(pct=50.0))  # ahead of plan, within tolerance
    now = at("2026-02-15", project(status="red", pct=40.0))  # behind, slipping
    found = insights.build(now, [stored(before)])
    kinds = kinds_of(found)
    assert ("breach.new", "A") in kinds and ("status.worse", "A") in kinds
    assert ("forecast.slipped", "A") in kinds and ("progress.stalled", "A") in kinds
    assert [i.severity for i in found] == sorted(
        (i.severity for i in found), key=["high", "medium", "low"].index)
    worse = next(i for i in found if i.kind == "status.worse")
    assert worse.severity == "high" and worse.fact_ids == ["project.A"]
    assert all(i.previous_report_id == "RPT-prev" for i in found)
    back = insights.build(before, [stored(now)])
    assert ("breach.cleared", "A") in kinds_of(back) and ("status.better", "A") in kinds_of(back)


def test_no_stall_when_reports_share_a_date():
    f = at("2026-02-01", project())
    assert insights.build(f, [stored(f)]) == []  # same day, same data: nothing changed


def test_a_new_risk_needs_a_previous_report_that_read_the_board():
    alert = [{"schema": "risk_alert.v1", "message_id": "m1",
              "data": {"project_id": "A", "severity": "high", "signal": "stalled", "mitigation":
                       "re-plan"}}]
    now = at("2026-02-01", project(), board=alert)
    unseen = insights.build(now, [stored(at("2026-01-25", project()))])
    assert "risk.new" not in {i.kind for i in unseen}  # the previous report could not see A4
    found = insights.build(now, [stored(at("2026-01-25", project(), board=[]))])
    [risk] = [i for i in found if i.kind == "risk.new"]
    assert risk.severity == "high" and risk.action == "re-plan" and risk.fact_ids == ["risk.m1"]


def test_spi_falling_three_reports_in_a_row():
    reports = [at(d, project(pct=p)) for d, p in
               (("2026-01-20", 40.0), ("2026-02-01", 50.0), ("2026-02-15", 55.0))]
    spis = [next(k.value for k in f.kpis if k.id == "kpi.spi") for f in reports]
    assert spis[0] > spis[1] > spis[2]
    found = insights.build(reports[2], [stored(reports[1]), stored(reports[0])])
    assert ("trend.spi_down", None) in kinds_of(found)


def narrative(summary, *, risks=(), lines=()):
    return ReportV1(scope=SCOPE, executive_summary=summary, project_status=list(lines),
                    key_risks=list(risks), recommended_actions=[])


def test_grounding_accepts_what_the_facts_say():
    alert = [{"schema": "risk_alert.v1", "message_id": "m1",
              "data": {"project_id": "B", "severity": "high",
                       "signal": "slack -7d, blocked ['T-3102']", "mitigation": "x"}}]
    f = at("2026-02-16", project(), project("B", "red", 20.0, "2026-02-20"), board=alert)
    b = next(p for p in f.projects if p.project_id == "B")
    text = (f"{SCOPE}: 2 projects in Q1 2026. B is red at 20% with SPI {b.spi:.2f}, forecast "
            f"{b.forecast_finish}, {abs(b.slack_days)} days past its deadline. T-3102 is blocked "
            f"(slack -7d).")
    lines = [ProjectStatusLine(project_id="B", name="B", status="red", percent_complete=20.0,
                               headline="behind")]
    g = grounding.check(narrative(text, lines=lines), f, SCOPE)
    assert g.ungrounded == [] and g.checked >= 6


def test_grounding_flags_made_up_figures_dates_and_projects():
    f = at("2026-02-16", project(), project("B", "red", 20.0))
    g = grounding.check(narrative(
        "B is 37% done and will finish 2026-07-01; PROJ-99 is fine.",
        lines=[ProjectStatusLine(project_id="B", name="B", status="amber", percent_complete=20.0,
                                 headline="")]), f, SCOPE)
    assert set(g.ungrounded) == {"37", "2026-07-01", "PROJ-99", "B: amber 20%"}
    assert not grounding.check(narrative("Average progress is 35%."), f, SCOPE).ungrounded


def _llm(report):
    return lambda system, user, schema, *, agent="?", model=None: report


def _run(monkeypatch, report):
    monkeypatch.setattr("ma_pmo.core.llm.complete_structured", _llm(report))
    ReportingAgent().run({"goal": "report", "task_ref": SCOPE, "kind": "executive",
                          "as_of": "2026-02-16"})
    rid, content = store.latest(SCOPE, "executive")
    return rid, ReportV2.model_validate(content)


def test_a5_keeps_a_grounded_llm_narrative(monkeypatch):
    ok = narrative("3 projects; PROJ-31 is red and forecast 7 days late.")
    rid, r = _run(monkeypatch, ok)
    assert r.path == "llm" and r.grounding and not r.grounding.ungrounded
    assert r.executive_summary == ok.executive_summary
    assert "match the facts" in render.render(r.model_dump(), rid, "md")


def test_a5_replaces_a_narrative_with_a_made_up_figure(monkeypatch):
    rid, r = _run(monkeypatch, narrative("PROJ-31 is 95% complete and on track."))
    assert r.path == "rule" and r.grounding and r.grounding.replaced
    assert "95" in r.grounding.ungrounded
    assert "95%" not in r.executive_summary
    assert "(rule-based automatic report)" in r.executive_summary
    assert "was replaced" in render.render(r.model_dump(), rid, "md")


def test_the_report_shows_what_changed():
    before = at("2026-02-01", project(pct=50.0))
    now = at("2026-02-15", project(status="red", pct=40.0))
    found = insights.build(now, [stored(before)])
    r = ReportV2(scope="P", path="rule", overall_status="red", facts=now, insights=found,
                 executive_summary="x", project_status=[])
    md = render.to_markdown(r, "RPT-1")
    assert "## Since the last report" in md and "▲▲ A went from green to red." in md
    first = ReportV2(scope="P", path="rule", overall_status="red", facts=before,
                     executive_summary="x", project_status=[])
    assert "first report of its kind" in render.to_markdown(first, "RPT-0")
