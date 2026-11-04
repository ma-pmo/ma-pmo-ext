"""Confidence calibration: metrics on known pairs, threshold what-if, and the report section."""
from __future__ import annotations

import pytest

from ma_pmo.eval.calibration import Pair, calibration, collect_pairs, threshold_table
from ma_pmo.eval.report import build_report, render


def _pairs(spec: list[tuple[float, bool]], **kw) -> list[Pair]:
    return [Pair(c, ok, "test", **kw) for c, ok in spec]


def test_perfectly_calibrated():
    # 0.8 → right 4 times in 5; 0.2 → right 1 time in 5
    pairs = _pairs([(0.8, True)] * 4 + [(0.8, False)] + [(0.2, True)] + [(0.2, False)] * 4)
    c = calibration(pairs)
    assert c["ece"] == 0.0 and c["verdict"] == "calibrated" and c["distinct_confidences"] == 2
    assert c["brier"] == pytest.approx(0.16)
    assert [b["accuracy"] for b in c["bins"]] == [0.2, 0.8]


def test_overconfident_and_uninformative():
    over = calibration(_pairs([(0.9, False)] * 3 + [(0.95, True)] * 2))
    assert over["verdict"] == "overconfident" and over["ece"] > 0.1
    flat = calibration(_pairs([(0.85, True)] * 3 + [(0.85, False)] * 3))
    assert flat["verdict"] == "uninformative"  # one value cannot separate right from wrong
    assert calibration(_pairs([(0.5, True)] * 4))["verdict"] == "insufficient"


def test_threshold_table_counts_flagged_messages_as_reviewed():
    pairs = _pairs([(0.4, False), (0.7, False), (0.9, True)]) + [Pair(0.95, False, "t", True)]
    by_t = {row["threshold"]: row for row in threshold_table(pairs, (0.5, 0.8))}
    assert by_t[0.5] == {"threshold": 0.5, "to_review": 2, "wrong_not_reviewed": 1,
                         "wrong_caught": 2}
    assert by_t[0.8] == {"threshold": 0.8, "to_review": 3, "wrong_not_reviewed": 0,
                         "wrong_caught": 3}


def test_collected_from_runs_and_shown_in_report():
    from ma_pmo.core.scenarios import run_scenario
    from ma_pmo.eval.harness import run_all

    run_scenario("quarterly_review")  # A4 publishes risk alerts with a confidence
    labels = {"PROJ-14": "medium", "PROJ-22": "low", "PROJ-31": "high"}
    pairs = collect_pairs("PORTFOLIO#2026-Q1", labels)
    assert any(p.source == "risk_alert" for p in pairs)
    results = run_all(populate=False, labels=labels)
    assert results["calibration"]["overall"]["n"] == len(pairs)
    report = build_report(results, scope="PORTFOLIO#2026-Q1", source="test")
    assert "## 4. Confidence calibration" in render(report, "md")
    assert "Confidence calibration" in render(report, "html")
