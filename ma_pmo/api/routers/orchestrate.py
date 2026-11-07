"""POST /orchestrate — A1 turns a goal into a workflow and runs it (see core/goals.py)."""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from ma_pmo.core.goals import run_goal

router = APIRouter(tags=["orchestrate"])


class OrchestrateRequest(BaseModel):
    goal: str
    task_ref: str = "PORTFOLIO#2026-Q1"
    thread_id: str | None = None
    pause_on_gate: bool = False


@router.post("/orchestrate")
def orchestrate(req: OrchestrateRequest) -> dict:
    return run_goal(req.goal, req.task_ref, thread_id=req.thread_id,
                    pause_on_gate=req.pause_on_gate)
