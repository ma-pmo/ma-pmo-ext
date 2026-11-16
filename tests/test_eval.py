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
    # five hypotheses plus the confidence-calibration check of the HITL threshold
    assert set(r.keys()) == {"H1", "H2", "H3", "H4", "H5", "calibration"}


def test_h5_note_follows_the_result():
    from ma_pmo.eval.harness import _h5_note

    assert "consistent" in _h5_note({"low": [0.6], "high": [0.4]})
    assert "no moderation effect" in _h5_note({"low": [0.4], "high": [0.6]})
    assert "Too few" in _h5_note({"low": [0.5], "high": []})


def test_a2_and_a6_cite_a7s_lessons_where_they_follow_it():
    """knowledge_kickoff: A2 reads A7 (upstream) and A6 reads it through review, so both cite the
    lessons; without A7 nothing does. H4 counts these, not A7's own answers."""
    from sqlalchemy import select

    from ma_pmo.core.scenarios import run_scenario
    from ma_pmo.db.models import AgentMessageRow
    from ma_pmo.db.session import get_session

    def citing(trace):
        with get_session() as s:
            rows = s.scalars(select(AgentMessageRow).where(
                AgentMessageRow.run_id == trace["run_id"])).all()
            return {r.sender for r in rows if r.sender != "A7" and any(
                e["kind"] == "knowledge" for e in (r.evidence or []))}

    with_a7 = run_scenario("knowledge_kickoff")
    assert citing(with_a7) == {"A2", "A6"}
    assert citing(run_scenario("knowledge_kickoff", drop_agents=("A7",))) == set()
    r = h4_knowledge_ablation()
    assert r["coverage_gain"] and set(r["citing_agents"]) >= {"A2", "A6"}
