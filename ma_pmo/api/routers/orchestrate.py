"""POST /orchestrate — feed a goal into the supervisor graph and run it."""
from __future__ import annotations

import uuid

from fastapi import APIRouter
from pydantic import BaseModel

from ma_pmo.api.deps import get_graph

router = APIRouter(tags=["orchestrate"])


class OrchestrateRequest(BaseModel):
    goal: str
    task_ref: str = "PORTFOLIO#2026-Q1"
    thread_id: str | None = None


@router.post("/orchestrate")
def orchestrate(req: OrchestrateRequest) -> dict:
    graph = get_graph()
    thread_id = req.thread_id or f"thread-{uuid.uuid4().hex[:8]}"
    config = {"configurable": {"thread_id": thread_id}}
    final = graph.invoke(
        {"goal": req.goal, "task_ref": req.task_ref, "outputs": [], "messages": []},
        config=config,
    )
    return {
        "thread_id": thread_id,
        "routing": final.get("routing"),
        "outputs": final.get("outputs", []),
        "synthesis": final.get("synthesis"),
    }
