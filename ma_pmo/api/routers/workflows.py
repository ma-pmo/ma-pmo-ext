"""Workflows, read-only: what each one runs, in which order, and which steps cannot be removed.

GET /workflows               : every loaded workflow, and the files that could not be loaded
GET /workflows/{workflow_id} : one workflow's steps, with what each waits for and its level
GET /runs/{run_id}/workflow  : the workflow a run used, with where each of its steps stands
GET /runs/{run_id}/board     : what each step of a run published, and what each step could read

Versions (see core/workflow_store.py):
POST /workflows/validate                               : the rules a spec breaks, if any
POST /workflows/dry-run                                : validate, then run on demo data (operator)
GET  /workflows/{workflow_id}/versions                 : every version, and which one is in use
GET  /workflows/{workflow_id}/versions/{version}       : one version, old ones included
POST /workflows/{workflow_id}/versions                 : save a draft (operator)
POST /workflows/{workflow_id}/versions/{version}/publish : put a draft in use (approver, admin)
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ma_pmo.agents import registry
from ma_pmo.api.auth import CurrentPrincipal
from ma_pmo.core import board, llm, runs, scenarios, workflow_store
from ma_pmo.core.i18n import tr
from ma_pmo.core.workflow import WorkflowSpec, builtin_ids

router = APIRouter(tags=["workflows"])


class Check(BaseModel):
    spec: dict[str, Any]


class Draft(Check):
    note: str = ""


def _invalid(e: workflow_store.Invalid) -> HTTPException:
    return HTTPException(status_code=422, detail={"problems": e.problems})


def _unknown(workflow_id: str, version: int | None = None) -> HTTPException:
    what = workflow_id if version is None else f"{workflow_id} v{version}"
    return HTTPException(status_code=404, detail=tr(
        f"unknown workflow '{what}'", f"없는 워크플로입니다: '{what}'"))


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
        "review": spec.review,
    }


@router.get("/workflows")
def list_workflows() -> dict:
    builtin, mine = builtin_ids(), set(workflow_store.published_all())
    return {"workflows": [{**_summary(spec, builtin), "published_here": spec.id in mine}
                          for spec in scenarios.workflows()],
            "problems": scenarios.workflow_problems,
            # what each model tier means here (core/llm.py)
            "models": {"standard": llm.model_for("standard"), "fast": llm.model_for("fast")}}


@router.get("/workflows/{workflow_id}")
def get_workflow(workflow_id: str) -> dict:
    try:
        spec = scenarios.workflow(workflow_id)
    except KeyError:
        raise _unknown(workflow_id) from None
    return {**_summary(spec, builtin_ids()), "steps": _steps(spec)}


@router.post("/workflows/validate")
def validate_workflow(body: Check) -> dict:
    """The same rules a draft and a publish must pass. Saves nothing."""
    _, found = workflow_store.problems(body.spec)
    return {"ok": not found, "problems": found}


@router.post("/workflows/dry-run")
def dry_run_workflow(body: Check) -> dict:
    """Run a spec on the demo data in a throwaway workspace; nothing real is touched."""
    from ma_pmo.core.dry_run import dry_run

    return dry_run(body.spec)


@router.get("/workflows/{workflow_id}/versions")
def list_versions(workflow_id: str) -> dict:
    found = workflow_store.versions(workflow_id)
    if not found:
        raise _unknown(workflow_id)
    return {"workflow": workflow_id, "versions": found}


@router.get("/workflows/{workflow_id}/versions/{version}")
def get_version(workflow_id: str, version: int) -> dict:
    try:
        spec = workflow_store.spec_of(workflow_id, version)
    except KeyError:
        raise _unknown(workflow_id, version) from None
    return {**_summary(spec, builtin_ids()), "steps": _steps(spec), "spec": spec.model_dump()}


@router.post("/workflows/{workflow_id}/versions", status_code=201)
def save_draft(workflow_id: str, body: Draft, principal: CurrentPrincipal) -> dict:
    try:
        return workflow_store.save_draft(body.spec, principal.subject, body.note, workflow_id)
    except workflow_store.Invalid as e:
        raise _invalid(e) from None


@router.post("/workflows/{workflow_id}/versions/{version}/publish")
def publish_version(workflow_id: str, version: int, principal: CurrentPrincipal) -> dict:
    try:
        return workflow_store.publish(workflow_id, version, principal.subject)
    except KeyError:
        raise _unknown(workflow_id, version) from None
    except workflow_store.Invalid as e:
        raise _invalid(e) from None


def _steps(spec: WorkflowSpec) -> list[dict]:
    needs, levels = spec.dependencies(), spec.levels()
    return [{"id": s.id, "agent": s.agent, "agent_name": registry.title(s.agent),
             "params": s.params, "needs": needs[s.id], "required": s.required,
             "model_tier": s.model_tier or "standard", "reads": s.reads, "level": levels[s.id]}
            for s in spec.steps]


def _saved_spec(run_id: str) -> tuple[dict, WorkflowSpec]:
    run = runs.get_run(run_id)
    saved = runs.get_state(run_id).get("spec") if run else None
    if run is None or not saved:
        raise HTTPException(status_code=404, detail=tr(
            f"no workflow saved for run '{run_id}'",
            f"이 실행에 저장된 워크플로가 없습니다: '{run_id}'"))
    return run, WorkflowSpec.model_validate(saved)


@router.get("/runs/{run_id}/workflow")
def run_workflow(run_id: str) -> dict:
    """The workflow exactly as this run saved it, which may differ from today's file."""
    run, spec = _saved_spec(run_id)
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


@router.get("/runs/{run_id}/board")
def run_board(run_id: str) -> dict:
    """Every post of the run, and per step its read mode and the steps it could read."""
    _run, spec = _saved_spec(run_id)
    steps = [{"id": s.id, "agent": s.agent, "reads": s.reads,
              "can_read": sorted(board.readable(spec, s.id) or [])} for s in spec.steps]
    return {"run_id": run_id, "workflow": spec.id, "steps": steps,
            "posts": board.posts(run_id, spec)}
