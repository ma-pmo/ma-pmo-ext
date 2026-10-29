"""Experiment spec — a data structure for declaring experiments.

Fluent builder:
    Experiment("h3", "risk detection check")
        .with_scenarios("risk_rebalance", "stage_gate_review")
        .repeat(5)
        .ablate("A7")           # compare A7 on/off
        .on_scope("PORTFOLIO#2026-Q1")
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ExperimentSpec:
    name: str
    description: str = ""
    #: scenario ids to run (empty list = all 20)
    scenarios: list[str] = field(default_factory=list)
    #: repetitions per scenario (for variance analysis)
    repeat: int = 1
    #: target portfolio
    scope: str = "PORTFOLIO#2026-Q1"
    #: ablation: agents to remove and compare (e.g. ["A7"])
    ablate_agents: list[str] = field(default_factory=list)


class Experiment:
    """Fluent builder for ExperimentSpec."""

    def __init__(self, name: str, description: str = "") -> None:
        self._spec = ExperimentSpec(name=name, description=description)

    def with_scenarios(self, *ids: str) -> Experiment:
        self._spec.scenarios = list(ids)
        return self

    def all_scenarios(self) -> Experiment:
        self._spec.scenarios = []
        return self

    def repeat(self, n: int) -> Experiment:
        self._spec.repeat = max(1, n)
        return self

    def on_scope(self, scope: str) -> Experiment:
        self._spec.scope = scope
        return self

    def ablate(self, *agents: str) -> Experiment:
        self._spec.ablate_agents = list(agents)
        return self

    def build(self) -> ExperimentSpec:
        return self._spec
