"""GET /eval — empirical results for hypotheses H1–H5 (§9)."""
from __future__ import annotations

from fastapi import APIRouter

from ma_pmo.eval.harness import run_all

router = APIRouter(tags=["eval"])


@router.get("/eval")
def evaluate(populate: bool = True) -> dict:
    """Compute H1–H5 metrics. With populate=True, deterministic agents fill the KPIs first."""
    return run_all(populate=populate)
