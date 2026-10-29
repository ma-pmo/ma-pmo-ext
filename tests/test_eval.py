"""eval harness — H1–H5 evidence."""
from __future__ import annotations

from ma_pmo.eval.harness import (
    h2_idle_rate,
    h3_risk_detection,
    h4_knowledge_ablation,
    h5_complexity,
    run_all,
)


def test_h3_precision_recall_against_ground_truth():
    r = h3_risk_detection()
    # fixtures: PROJ-31 (red, high), PROJ-14 (amber, medium), PROJ-22 (green, low)
    # rule-based detection must flag PROJ-31/PROJ-14 as positives -> recall = 1.0
    assert r["recall"] == 1.0
    assert r["precision"] is not None
    assert r["f1"] is not None
    assert r["confusion"]["tp"] >= 2


def test_h2_uses_utilization_kpi():
    from ma_pmo.eval.harness import populate_deterministic_kpis

    populate_deterministic_kpis()
    r = h2_idle_rate()
    assert r["utilization_avg_pct"] is not None
    assert r["target_utilization_pct"] == 80


def test_h4_knowledge_ablation_shows_coverage_gain():
    r = h4_knowledge_ablation()
    assert r["a7_enabled"]["citations"] > r["a7_disabled"]["citations"]


def test_h5_complexity_stratification():
    r = h5_complexity()
    assert "low" in r["strata"] and "high" in r["strata"]


def test_run_all_returns_five_hypotheses():
    r = run_all(populate=True)
    assert set(r.keys()) == {"H1", "H2", "H3", "H4", "H5"}
