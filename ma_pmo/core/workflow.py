"""Workflows as data — which agents run, in what order, with which parameters.

A `WorkflowSpec` is validated once, wherever it comes from. The built-in lifecycle scenarios
live in `fixtures/workflows.json`; your own go in the folder `MA_PMO_WORKFLOWS_DIR` (default
`./workflows`), one JSON file each. A file that fails validation is reported by
`load_workflows` and skipped, like a broken plugin.

A step's `needs` lists the steps it waits for; left out, it follows the step before it.
`required` marks a step that must stay in the workflow, such as a governance gate.
`model_tier` picks the LLM for the step's agent: `standard` (`LLM_MODEL`, the default) or `fast`
(`LLM_MODEL_FAST`), see core/llm.py.
`reads` says which earlier posts the step's agent may read (core/board.py): `isolated` (the
default: none, only its own data), `upstream` (what the steps it waits for, directly or not,
published) or `board` (what every step of an earlier stage published).
Every run is reviewed unless the workflow says `"review": false` (`with_review`): the decision
steps of A5 and A6 read what they wait for and review their own output, and a dedicated reviewer
(A8) runs last and reviews every decision on the board. See docs/REVIEW.md; the evaluation that
turned it on by default is docs/REVIEW-EVAL.md.
"""
from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError, model_validator

from ma_pmo.core.config import get_settings

_BUILTIN = Path(__file__).resolve().parent.parent / "fixtures" / "workflows.json"
BUILDERS = {"A5", "A6"}  # agents that review their own decisions when they may read
AUDITOR = "A8"


class Text(BaseModel):
    en: str
    ko: str

    @property
    def pair(self) -> tuple[str, str]:
        return self.en, self.ko


class WorkflowStep(BaseModel):
    id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
    agent: str
    params: dict[str, Any] = Field(default_factory=dict)
    needs: list[str] | None = None
    required: bool = False
    model_tier: Literal["standard", "fast"] | None = None  # None: standard
    reads: Literal["isolated", "upstream", "board"] = "isolated"


class WorkflowSpec(BaseModel):
    id: str
    version: int = 1
    title: Text
    category: str = "custom"
    goal: Text
    description: Text
    hypotheses: list[str] = Field(default_factory=list)
    steps: list[WorkflowStep]
    ablated: bool = False  # agents were removed for an experiment; may leave no steps
    review: bool = True  # review every run (with_review); "review": false opts a workflow out

    @model_validator(mode="after")
    def _check_steps(self) -> WorkflowSpec:
        if not self.steps and not self.ablated:
            raise ValueError("a workflow needs at least one step")
        ids = [s.id for s in self.steps]
        if len(set(ids)) != len(ids):
            raise ValueError(f"step ids must be unique: {ids}")
        for step in self.steps:
            unknown = set(step.needs or []) - set(ids)
            if unknown:
                raise ValueError(f"step {step.id} needs unknown steps: {sorted(unknown)}")
        self._check_cycles()
        return self

    def without_agents(self, agents: Iterable[str]) -> WorkflowSpec:
        """This workflow minus some agents (ablation). What followed them follows what is left."""
        dropped = set(agents)
        if not dropped:
            return self
        removed = {s.id for s in self.steps if s.agent in dropped}
        steps = [
            s.model_copy(update={"needs": None if s.needs is None
                                 else [n for n in s.needs if n not in removed]})
            for s in self.steps if s.id not in removed
        ]
        return self.model_copy(update={"steps": steps, "ablated": True})

    def with_review(self) -> WorkflowSpec:
        """The workflow as a reviewed run executes it; itself when `review` is off.

        Isolated A5 and A6 steps read `upstream`, so they review their own decisions, and an A8
        step that waits for every last step and reads the whole `board` is added at the end.
        A spec that already has an A8 step is left as it is, so applying this twice is safe.
        """
        if not self.review or any(s.agent == AUDITOR for s in self.steps) or not self.steps:
            return self
        deps = self.dependencies()
        waited_for = {n for needs in deps.values() for n in needs}
        steps = [s.model_copy(update={"reads": "upstream"})
                 if s.agent in BUILDERS and s.reads == "isolated" else s for s in self.steps]
        step_id, n = "review", 2
        while step_id in deps:
            step_id, n = f"review_{n}", n + 1
        steps.append(WorkflowStep(id=step_id, agent=AUDITOR, reads="board",
                                  needs=[s for s in deps if s not in waited_for]))
        return self.model_copy(update={"steps": steps})

    def dependencies(self) -> dict[str, list[str]]:
        """Each step's prerequisites, with the default of following the step before it."""
        deps: dict[str, list[str]] = {}
        previous: str | None = None
        for step in self.steps:
            default = [previous] if previous else []
            deps[step.id] = step.needs if step.needs is not None else default
            previous = step.id
        return deps

    def upstream(self, step_id: str) -> set[str]:
        """Every step `step_id` waits for, directly or through others."""
        deps, found = self.dependencies(), set()
        todo = list(deps[step_id])
        while todo:
            step = todo.pop()
            if step not in found:
                found.add(step)
                todo += deps[step]
        return found

    def levels(self) -> dict[str, int]:
        """How many steps must finish before each one can start, along the longest chain.

        Steps on the same level can run in parallel; this is how the workflow view lays them out.
        """
        deps = self.dependencies()
        level: dict[str, int] = {}
        for wave, ready in enumerate(self._waves(deps)):
            level.update(dict.fromkeys(ready, wave))
        return {s: level[s] for s in deps}

    @staticmethod
    def _waves(deps: dict[str, list[str]]) -> list[set[str]]:
        done: set[str] = set()
        waves: list[set[str]] = []
        while len(done) < len(deps):
            ready = {s for s, needs in deps.items() if s not in done and set(needs) <= done}
            if not ready:
                raise ValueError(f"steps depend on each other: {sorted(set(deps) - done)}")
            waves.append(ready)
            done |= ready
        return waves

    def _check_cycles(self) -> None:
        self._waves(self.dependencies())


def builtin_ids() -> set[str]:
    """The ids of the workflows that ship with MA-PMO."""
    return {w["id"] for w in json.loads(_BUILTIN.read_text(encoding="utf-8"))}


def load_workflows(known_agents: set[str], directory: str | Path | None = None,
                   ) -> tuple[dict[str, WorkflowSpec], list[str]]:
    """Built-in workflows plus valid ones from `directory`, and what was wrong with the rest."""
    raw = json.loads(_BUILTIN.read_text(encoding="utf-8"))
    specs = {spec.id: spec for spec in map(WorkflowSpec.model_validate, raw)}
    problems: list[str] = []
    folder = Path(directory if directory is not None else get_settings().workflows_dir)
    for path in sorted(folder.glob("*.json")) if folder.is_dir() else []:
        try:
            spec = WorkflowSpec.model_validate_json(path.read_text(encoding="utf-8"))
        except (ValidationError, OSError, UnicodeDecodeError) as e:
            problems.append(f"{path.name}: {str(e)[:200]}")
            continue
        unknown = sorted({s.agent for s in spec.steps} - known_agents)
        if unknown:
            problems.append(f"{path.name}: unknown agents {unknown}")
        elif spec.id in specs:
            problems.append(f"{path.name}: id '{spec.id}' is already used")
        else:
            specs[spec.id] = spec
    return specs, problems
