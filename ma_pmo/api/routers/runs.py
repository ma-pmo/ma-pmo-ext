"""GET /runs — what ran, step by step, and how it ended."""
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
