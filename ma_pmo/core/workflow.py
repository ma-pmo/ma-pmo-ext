"""Workflows as data — which agents run, in what order, with which parameters.

A `WorkflowSpec` is validated once, wherever it comes from. The built-in lifecycle scenarios
live in `fixtures/workflows.json`; your own go in the folder `MA_PMO_WORKFLOWS_DIR` (default
`./workflows`), one JSON file each. A file that fails validation is reported by
`load_workflows` and skipped, like a broken plugin.

A step's `needs` lists the steps it waits for; left out, it follows the step before it.
`required` marks a step that must stay in the workflow, such as a governance gate.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, ValidationError, model_validator

from ma_pmo.core.config import get_settings

_BUILTIN = Path(__file__).resolve().parent.parent / "fixtures" / "workflows.json"


class Text(BaseModel):
    en: str
    ko: str

    @property
    def pair(self) -> tuple[str, str]:
        return self.en, self.ko


class WorkflowStep(BaseModel):
    id: str
    agent: str
    params: dict[str, Any] = Field(default_factory=dict)
    needs: list[str] | None = None
    required: bool = False


class WorkflowSpec(BaseModel):
    id: str
    version: int = 1
    title: Text
    category: str = "custom"
    goal: Text
    description: Text
    hypotheses: list[str] = Field(default_factory=list)
    steps: list[WorkflowStep]

    @model_validator(mode="after")
    def _check_steps(self) -> WorkflowSpec:
        if not self.steps:
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

    def dependencies(self) -> dict[str, list[str]]:
        """Each step's prerequisites, with the default of following the step before it."""
        deps: dict[str, list[str]] = {}
        previous: str | None = None
        for step in self.steps:
            default = [previous] if previous else []
            deps[step.id] = step.needs if step.needs is not None else default
            previous = step.id
        return deps

    def _check_cycles(self) -> None:
        deps = self.dependencies()
        done: set[str] = set()
        while len(done) < len(deps):
            ready = {s for s, needs in deps.items() if s not in done and set(needs) <= done}
            if not ready:
                raise ValueError(f"steps depend on each other: {sorted(set(deps) - done)}")
            done |= ready


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
