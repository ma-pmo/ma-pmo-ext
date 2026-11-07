"""GET /runs — what ran, step by step, and how it ended. POST to continue a stopped run."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ma_pmo.core import runs

router = APIRouter(tags=["runs"])


@router.get("/runs")
def list_runs(status: str | None = None, limit: int = 50) -> list[dict]:
    return runs.list_runs(status, max(1, min(limit, 200)))


@router.get("/runs/{run_id}")
def get_run(run_id: str) -> dict:
    run = runs.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")
    return run


@router.post("/runs/{run_id}/resume")
def resume_run(run_id: str) -> dict:
    """Continue a paused or interrupted run. 409 if it cannot continue now."""
    from ma_pmo.core.executor import resume_run

    try:
        return resume_run(run_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail="run not found") from e
    except runs.NotResumable as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
