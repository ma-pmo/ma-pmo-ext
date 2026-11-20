"""Roadmap 11, step 1: A4's confidence comes from its evidence, calibrated on the benchmark."""
from __future__ import annotations

import json

from ma_pmo.agents import risk_calibration
from ma_pmo.agents.risk import RiskAgent
from ma_pmo.agents.risk_signals import ProjectSignals
from ma_pmo.benchmark.calibrate import fit, wilson
from ma_pmo.benchmark.run import Row

TABLE = {"kinds": {"blocked": {"rate": 0.6}, "stalled": {"rate": 0.9}, "moving": {"rate": 0.2}}}


def sig(blocked=(), stalled=()):
    return ProjectSignals(project_id="P", status="amber", percent_complete=10.0,
                          schedule_slack_days=0, completion_gap_pct=90.0,
                          blocked_tasks=list(blocked), stalled_tasks=list(stalled))


def test_alert_confidence_is_the_mean_over_the_tasks_it_names():
    project = {"tasks": [{"task_id": t, "percent_complete": p}
                         for t, p in (("a", 0), ("b", 0), ("c", 50), ("d", 100))]}
    assert risk_calibration.alert_confidence(sig(["a"], ["b"]), project, TABLE) == 0.75
    assert risk_calibration.alert_confidence(sig(stalled=["b"]), project, TABLE) == 0.9
    # an alert that names no task (status only): the project's open tasks, all moving here
    assert risk_calibration.alert_confidence(sig(), project, TABLE) == 0.2
    assert risk_calibration.alert_confidence(sig(), {"tasks": []}, TABLE) == 0.2


def test_the_bundled_table_comes_from_the_benchmark():
    table = risk_calibration.load()
    assert set(table["kinds"]) == set(risk_calibration.KINDS)
    assert table["test"]["ece_calibrated"] < table["test"]["ece_fixed"]
    for kind in table["kinds"].values():
        lo, hi = kind["ci95"]
        assert lo <= kind["rate"] <= hi and kind["n"] > 0


def test_another_table_can_be_used(tmp_path, monkeypatch):
    own = tmp_path / "mine.json"
    own.write_text(json.dumps(TABLE), encoding="utf-8")
    risk_calibration.load.cache_clear()
    monkeypatch.setenv("MA_PMO_A4_CALIBRATION", str(own))
    try:
        assert risk_calibration.task_probability("stalled") == 0.9
    finally:
        monkeypatch.delenv("MA_PMO_A4_CALIBRATION")
        risk_calibration.load.cache_clear()


def test_a4_reports_calibrated_confidence_on_the_demo():
    out = RiskAgent().run({"task_ref": "PORTFOLIO#2026-Q1"})
    by_project = {m["task_ref"].split("/")[1]: m["confidence"] for m in out["messages"]}
    table = risk_calibration.load()["kinds"]
    # PROJ-14 is blocked on one task; PROJ-31 has a stalled and a blocked one
    assert by_project["PROJ-14"] == round(table["blocked"]["rate"], 2)
    assert by_project["PROJ-31"] == round((table["blocked"]["rate"] + table["stalled"]["rate"])
                                          / 2, 2)
    assert len(set(by_project.values())) > 1  # no longer one value for everything


def test_fitting_the_table():
    from datetime import date

    def row(a4, label):
        return Row(("C", "1"), "C", date(2020, 1, 1), "K", {}, a4, label)

    rows = [row(0.9, 1)] * 3 + [row(0.9, 0)] + [row(0.7, 1)] * 2 + [row(0.3, 0)] * 4
    kinds = fit(rows)
    assert (kinds["blocked"]["rate"], kinds["stalled"]["rate"], kinds["moving"]["rate"]) == (
        0.75, 1.0, 0.0)
    assert kinds["blocked"]["n"] == 4 and kinds["blocked"]["slipped"] == 3
    lo, hi = wilson(3, 4)
    assert 0.2 < lo < 0.75 < hi < 1.0
    assert wilson(0, 0) == (0.0, 1.0)


def test_clopper_pearson_upper_bound():
    from ma_pmo.core.risk_control import upper_bound

    assert abs(upper_bound(0, 10, 0.1) - (1 - 0.1 ** (1 / 10))) < 1e-6  # closed form at 0
    assert upper_bound(5, 100, 0.1) > 0.05 and upper_bound(5, 100, 0.1) < 0.1
    assert upper_bound(50, 1000, 0.1) < upper_bound(5, 100, 0.1)  # more data, tighter
    assert upper_bound(0, 0, 0.1) == 1.0 and upper_bound(3, 3, 0.1) == 1.0


def test_threshold_keeps_committed_errors_under_alpha():
    from ma_pmo.core.risk_control import NOBODY, Group, threshold

    groups = [Group(0.9, 1000, 50), Group(0.7, 1000, 150), Group(0.4, 1000, 500)]
    assert threshold(groups, alpha=0.08) == 0.9  # 5% alone; adding 0.7 makes 10%
    assert threshold(groups, alpha=0.12) == 0.7
    assert threshold(groups, alpha=0.3) == 0.4  # 23% with everything committed
    assert threshold(groups, alpha=0.01) == NOBODY  # nothing is good enough
    # fixed sequence: a failing group stops the search even if lower ones would pass again
    assert threshold([Group(0.9, 100, 40), Group(0.5, 10000, 0)], alpha=0.1) == NOBODY


def test_a4_alerts_use_the_risk_controlled_threshold(monkeypatch):
    from ma_pmo.core import risk_control
    from ma_pmo.core.config import get_settings

    settings = get_settings()
    assert risk_control.threshold_for("A4", 0.6) == 0.6  # off by default
    monkeypatch.setattr(settings, "hitl_risk_alpha", 0.15)
    tau = risk_control.threshold_for("A4", 0.6)
    assert tau == risk_control.a4_threshold(0.15) and 0.6 < tau < 1
    assert risk_control.threshold_for("A2", 0.6) == 0.6  # other agents keep the fixed one
    monkeypatch.setattr(settings, "hitl_risk_alpha", 0.0001)
    assert risk_control.threshold_for("A4", 0.6) == risk_control.NOBODY
