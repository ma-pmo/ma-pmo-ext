"""Workflows, read-only: what each one runs, in which order, and which steps cannot be removed.

GET /workflows               : every loaded workflow, and the files that could not be loaded
GET /workflows/{workflow_id} : one workflow's steps, with what each waits for and its level
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ma_pmo.agents import registry
from ma_pmo.core import scenarios
from ma_pmo.core.i18n import tr
from ma_pmo.core.workflow import WorkflowSpec, builtin_ids

router = APIRouter(tags=["workflows"])


def _summary(spec: WorkflowSpec, builtin: set[str]) -> dict:
    return {
        "id": spec.id,
        "version": spec.version,
        "title": tr(*spec.title.pair),
        "category_id": spec.category,
        "category": tr(*scenarios.CATEGORIES.get(spec.category, (spec.category, spec.category))),
        "goal": tr(*spec.goal.pair),
        "description": tr(*spec.description.pair),
        "hypotheses": spec.hypotheses,
        "source": "builtin" if spec.id in builtin else "custom",
        "agents": [s.agent for s in spec.steps],
    }


@router.get("/workflows")
def list_workflows() -> dict:
    builtin = builtin_ids()
    return {"workflows": [_summary(spec, builtin) for spec in scenarios.workflows()],
            "problems": scenarios.workflow_problems}


@router.get("/workflows/{workflow_id}")
def get_workflow(workflow_id: str) -> dict:
    try:
        spec = scenarios.workflow(workflow_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=tr(
            f"unknown workflow '{workflow_id}'", f"없는 워크플로입니다: '{workflow_id}'")) from None
    needs, levels = spec.dependencies(), spec.levels()
    steps = [{"id": s.id, "agent": s.agent, "agent_name": registry.title(s.agent),
              "params": s.params, "needs": needs[s.id], "required": s.required,
              "level": levels[s.id]} for s in spec.steps]
    return {**_summary(spec, builtin_ids()), "steps": steps}
