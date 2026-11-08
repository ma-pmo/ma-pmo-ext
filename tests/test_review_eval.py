"""The review ablation (ma_pmo/eval/review.py): its cases, its numbers and what it leaves behind."""
from __future__ import annotations

from ma_pmo.agents import registry
from ma_pmo.cli import main as cli
from ma_pmo.core import llm
from ma_pmo.core.config import get_settings
from ma_pmo.eval import review


def test_the_cases_are_labelled_by_what_the_agents_produce():
    chosen = review.cases()
    assert len(chosen) == 35 and sum(c.control for c in chosen) == 12  # a third are controls
    result = review.evaluate(("main",), chosen)
    assert result["labels_ok"] is True and result["mislabelled"] == []
    assert (result["gate_conflicts"], result["report_conflicts"]) == (25, 6)


def test_the_commit_gate_is_what_brings_conflicts_to_a_person():
    result = review.evaluate(("+auditor", "+commit gate"))
    before, after = result["summary"]["+auditor"], result["summary"]["+commit gate"]
    assert before["surfaced"][0] == 0.0 and before["wrong_commit"][0] == 1.0
    assert after["surfaced"] == (1.0, 1.0, 1.0) and after["wrong_commit"][0] == 0.0
    assert after["false_hold"][0] == 0.0 and after["report_fixed"][0] == 1.0
    assert after["llm_calls"] == 0  # the deterministic path costs nothing more
    assert after["alternatives"] == 0.0  # off unless MA_PMO_REVIEW_ALTERNATIVES


def test_review_asks_nothing_new_of_people_on_the_demo_data():
    workload = review.demo_workload()
    assert len(workload) == 20 and sum(w["new"] for w in workload) == 0
    held = [w for w in workload if w["held"]]
    assert held and all(w["why"] == ["gate.no_open_high_risk"] for w in held)


def test_the_evaluation_leaves_nothing_behind():
    agents, completion = dict(registry._instances), llm.litellm.completion
    alternatives = get_settings().review_alternatives
    result = review.evaluate(("main", "+alternatives"), review.cases()[:3])
    assert result["summary"]["+alternatives"]["alternatives"] > 0
    assert registry._instances == agents and llm.litellm.completion is completion
    assert get_settings().review_alternatives == alternatives
    table = review.to_markdown(result)
    assert table.count("\n| ") == 3 and "| +alternatives |" in table


def test_the_cli_prints_both_tables(monkeypatch, capsys):
    result = review.evaluate(("main",), review.cases()[:2])
    monkeypatch.setattr(review, "evaluate", lambda: result)
    monkeypatch.setattr(review, "demo_workload", lambda: [
        {"scenario": "s", "decisions": 2, "held": 1, "new": 0, "annotated": 1,
         "why": ["gate.no_open_high_risk"], "ms_off": 10.0, "ms_on": 12.0}])
    assert cli(["eval", "--review"]) == 0
    out = capsys.readouterr().out
    assert "| main |" in out and "| s | 2 | 1 | 0 | 1 |" in out and "| **all** |" in out


def test_a_held_decision_counts_only_when_its_challenges_name_the_conflict():
    case = review.Case("t", {}, {review.RISK, review.STAFFED})
    outputs = [
        {"schema": "gate_review.v1", "data": {"project_id": "PROJ-X", "decision": "pass"}},
        {"schema": "allocation.v1", "data": {"plan": [], "unstaffed": []}},
        {"schema": "report.v1", "data": {"key_risks": []}},
    ]
    decided = [{"schema": "gate_review.v1", "project_id": "PROJ-X", "message_id": "m",
                "status": "review_pending"}]

    def held_with(*constraints):
        pending = [{"message_id": "m", "review": {"challenges": [
            {"constraint": c} for c in constraints], "alternatives": []}}]
        return review._measure(case, outputs, decided, pending, 0, 1, 1.0)

    assert held_with(review.RISK, review.STAFFED)["surfaced"] == 2
    assert held_with(review.RISK)["surfaced"] == 0  # held, but one side is missing
    assert held_with()["surfaced"] == 0 and held_with()["wrong_commit"] is False
