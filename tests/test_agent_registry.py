"""Agent registry: one source for workers, routing and names; agents are built on first use."""
from __future__ import annotations

import pytest

from ma_pmo.agents import registry
from ma_pmo.agents.orchestrator import OrchestratorAgent
from ma_pmo.agents.orchestrator_rules import keyword_route
from ma_pmo.core.i18n import use_lang
from ma_pmo.core.scenarios import SCENARIOS
from ma_pmo.core.schemas.payloads import PAYLOAD_REGISTRY


@pytest.mark.smoke
def test_builtin_workers_are_complete_and_valid():
    specs = registry.specs()
    assert set(specs) == {"A2", "A3", "A4", "A5", "A6", "A7"}
    for agent_id, spec in specs.items():
        assert spec.output_schema in PAYLOAD_REGISTRY, agent_id
        agent = registry.get(agent_id)
        assert agent.agent_id == agent_id  # the spec and the class agree
        assert registry.get(agent_id) is agent  # one shared instance


def test_every_scenario_uses_registered_workers():
    used = {a for scen in SCENARIOS.values() for a, _ in scen["steps"]}
    assert used <= set(registry.specs())


def test_agents_are_built_on_first_use(monkeypatch):
    built = []
    spec = registry.BUILTINS[0]
    monkeypatch.setattr(registry, "_instances", {})
    monkeypatch.setattr(registry, "BUILTINS", (registry.AgentSpec(
        **{**spec.__dict__, "factory": lambda: built.append(1) or object()}),))
    assert list(registry.WORKERS) == [spec.id] and len(registry.WORKERS) == 1
    assert built == []  # listing workers builds nothing
    registry.WORKERS[spec.id]
    registry.WORKERS[spec.id]
    assert built == [1]


def test_unknown_agent():
    with pytest.raises(KeyError):
        registry.get("A9")
    assert registry.title("A9") == "A9"


@pytest.mark.regression
@pytest.mark.parametrize("goal, agents", [
    ("Q1 portfolio report with risks", ["A5", "A4"]),
    ("리스크와 일정 점검", ["A4", "A2"]),
    ("자원 배분과 게이트 심사", ["A3", "A6"]),
    ("유사 사례 교훈 찾아줘", ["A7"]),
    ("hello", ["A5"]),  # nothing matches: safe default
])
def test_rule_based_routing_is_unchanged(goal, agents):
    assert [d.agent for d in keyword_route(goal).delegations] == agents


def test_names_and_prompt_come_from_the_registry():
    with use_lang("ko"):
        assert registry.title("A2") == "계획"
    with use_lang("en"):
        assert registry.title("A2") == "Planning"
    prompt = OrchestratorAgent().role_prompt
    for agent_id, spec in registry.specs().items():
        assert f"- {agent_id} {spec.capability}" in prompt
