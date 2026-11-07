"""What the LLM calls cost (see core/costs.py).

GET /costs                : totals and one row per model, agent, run, workflow or day
GET /runs/{run_id}/costs  : one run, per step
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ma_pmo.core import costs, runs
from ma_pmo.core.i18n import tr

router = APIRouter(tags=["costs"])


@router.get("/costs")
def cost_summary(by: str = "model", days: int | None = None) -> dict:
    if by not in costs.GROUPS or by == "step":
        raise HTTPException(status_code=422, detail=tr(
            "by must be model, agent, run, workflow, day or purpose",
            "by는 model, agent, run, workflow, day, purpose 중 하나여야 합니다"))
    return costs.summary(by, days=days if days and days > 0 else None)


@router.get("/runs/{run_id}/costs")
def run_costs(run_id: str) -> dict:
    if runs.get_run(run_id) is None:
        raise HTTPException(status_code=404, detail="run not found")
    return {"run_id": run_id, **costs.summary("step", run_id=run_id)}
