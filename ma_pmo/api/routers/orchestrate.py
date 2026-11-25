"""POST /orchestrate — A1 turns a goal into a workflow and runs it (see core/goals.py)."""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from ma_pmo.api.auth import ANONYMOUS, CurrentPrincipal
from ma_pmo.core.goals import run_goal
from ma_pmo.core.scope import DEFAULT_SCOPE

router = APIRouter(tags=["orchestrate"])


class OrchestrateRequest(BaseModel):
    goal: str
    task_ref: str = DEFAULT_SCOPE
    thread_id: str | None = None
    pause_on_gate: bool = False


@router.post("/orchestrate")
def orchestrate(req: OrchestrateRequest, principal: CurrentPrincipal) -> dict:
    from fastapi import HTTPException

    from ma_pmo.core import safety

    try:  # a goal that carries instructions to the model (roadmap 10)
        safety.guard_input(req.goal, "goal")
    except safety.InputBlocked as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    from ma_pmo.core import duties

    with duties.requested_by(None if principal is ANONYMOUS else principal.subject):
        return run_goal(req.goal, req.task_ref, thread_id=req.thread_id,
                        pause_on_gate=req.pause_on_gate)
