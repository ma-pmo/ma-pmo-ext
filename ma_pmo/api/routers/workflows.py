"""Workflows, read-only: what each one runs, in which order, and which steps cannot be removed.

GET /workflows               : every loaded workflow, and the files that could not be loaded
GET /workflows/{workflow_id} : one workflow's steps, with what each waits for and its level
GET /runs/{run_id}/workflow  : the workflow a run used, with where each of its steps stands
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ma_pmo.agents import registry
from ma_pmo.core import runs, scenarios
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
    return {**_summary(spec, builtin_ids()), "steps": _steps(spec)}


def _steps(spec: WorkflowSpec) -> list[dict]:
    needs, levels = spec.dependencies(), spec.levels()
    return [{"id": s.id, "agent": s.agent, "agent_name": registry.title(s.agent),
             "params": s.params, "needs": needs[s.id], "required": s.required,
             "level": levels[s.id]} for s in spec.steps]


@router.get("/runs/{run_id}/workflow")
def run_workflow(run_id: str) -> dict:
    """The workflow exactly as this run saved it, which may differ from today's file."""
    run = runs.get_run(run_id)
    saved = runs.get_state(run_id).get("spec") if run else None
    if run is None or not saved:
        raise HTTPException(status_code=404, detail=tr(
            f"no workflow saved for run '{run_id}'",
            f"이 실행에 저장된 워크플로가 없습니다: '{run_id}'"))
    spec = WorkflowSpec.model_validate(saved)
    states = runs.step_states(run_id)
    steps = [{**step, "run": states.get(seq, {"status": "not_started", "pending_approvals": 0})}
             for seq, step in enumerate(_steps(spec), start=1)]
    try:
        same = scenarios.workflow(spec.id).model_dump() == spec.model_dump()
    except KeyError:  # an orchestrated goal, or a workflow file removed since
        same = False
    summary = {k: v for k, v in run.items() if k not in ("steps", "result")}
    return {**_summary(spec, builtin_ids()), "steps": steps, "run": summary,
            "same_as_current": same}
