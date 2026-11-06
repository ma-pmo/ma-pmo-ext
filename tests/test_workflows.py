"""Workflows as data: validation, your own files, and the golden traces of the 20 scenarios."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from ma_pmo.agents import registry
from ma_pmo.core import scenarios
from ma_pmo.core.workflow import WorkflowSpec, load_workflows

ROOT = Path(__file__).resolve().parents[1]
TEXT = {"en": "x", "ko": "엑스"}


def _spec(steps, **extra) -> dict:
    return {"id": "mine", "title": TEXT, "goal": TEXT, "description": TEXT, "steps": steps, **extra}


@pytest.mark.regression
def test_golden_traces_match(tmp_path):
    """Every scenario, in both languages, in a fresh database: same agents, order and output."""
    env = {**os.environ, "PYTHONPATH": str(ROOT), "ANTHROPIC_API_KEY": "test-key",
           "DB_URL": f"sqlite:///{tmp_path / 'g.db'}",
           "CHECKPOINT_DB": str(tmp_path / "c.sqlite")}
    run = subprocess.run([sys.executable, str(ROOT / "tests/golden/capture.py")], cwd=tmp_path,
                         env=env, capture_output=True, text=True, timeout=300)
    assert run.returncode == 0, run.stderr[-800:]
    actual = json.loads(run.stdout[run.stdout.index("{"):])
    expected = json.loads((ROOT / "tests/golden/scenario_traces.json").read_text(encoding="utf-8"))
    assert set(actual) == set(expected)
    different = [k for k in expected if actual[k] != expected[k]]
    assert not different, f"traces changed: {different[:5]}"


def test_builtin_workflows_are_valid_and_gates_are_required():
    specs, problems = load_workflows(set(registry.specs()), directory="/nonexistent")
    assert len(specs) == 20 and problems == []
    gates = [s for spec in specs.values() for s in spec.steps if "gate" in s.params]
    assert gates and all(s.required for s in gates)


def test_steps_follow_each_other_unless_they_say_otherwise():
    spec = WorkflowSpec.model_validate(_spec([
        {"id": "a", "agent": "A2"}, {"id": "b", "agent": "A4"},
        {"id": "c", "agent": "A5", "needs": ["a"]}, {"id": "d", "agent": "A7", "needs": []},
    ]))
    assert spec.dependencies() == {"a": [], "b": ["a"], "c": ["a"], "d": []}


@pytest.mark.parametrize("steps, reason", [
    ([], "at least one step"),
    ([{"id": "a", "agent": "A2"}, {"id": "a", "agent": "A4"}], "unique"),
    ([{"id": "a", "agent": "A2", "needs": ["z"]}], "unknown steps"),
    ([{"id": "a", "agent": "A2", "needs": ["b"]}, {"id": "b", "agent": "A4", "needs": ["a"]}],
     "depend on each other"),
    ([{"id": "a", "agent": "A2", "needs": ["a"]}], "depend on each other"),
])
def test_invalid_workflows_are_rejected(steps, reason):
    with pytest.raises(ValidationError, match=reason):
        WorkflowSpec.model_validate(_spec(steps))


@pytest.fixture
def restore():
    yield
    scenarios.reload_workflows("/nonexistent")


def test_your_own_workflow_runs_like_a_scenario(tmp_path, restore):
    spec = _spec([{"id": "plan", "agent": "A2"}, {"id": "report", "agent": "A5"}],
                 hypotheses=["H1"])
    (tmp_path / "mine.json").write_text(json.dumps(spec), encoding="utf-8")
    assert scenarios.reload_workflows(str(tmp_path)) == []
    assert any(s["id"] == "mine" and s["category_id"] == "custom"
               for s in scenarios.list_scenarios())
    trace = scenarios.run_scenario("mine")
    assert trace["status"] == "succeeded"
    assert [p["agent"] for p in trace["phases"] if p["phase"] == "execute"] == ["A2", "A5"]


def test_bad_files_are_reported_and_skipped(tmp_path, restore):
    (tmp_path / "broken.json").write_text("{not json", encoding="utf-8")
    (tmp_path / "ghost.json").write_text(json.dumps(
        {**_spec([{"id": "a", "agent": "acme.ghost"}]), "id": "ghost"}), encoding="utf-8")
    (tmp_path / "taken.json").write_text(json.dumps(
        {**_spec([{"id": "a", "agent": "A2"}]), "id": "weekly_status"}), encoding="utf-8")
    problems = scenarios.reload_workflows(str(tmp_path))
    assert len(problems) == 3
    assert any("acme.ghost" in p for p in problems) and any("already used" in p for p in problems)
    assert len(scenarios.SCENARIOS) == 20
