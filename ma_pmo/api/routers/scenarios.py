"""Agent collaboration scenarios — demonstrating the paper's validity.

GET  /scenarios          : list available use cases
POST /scenarios/{id}/run : four-phase trace (plan -> execute -> complete -> insight)
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ma_pmo.core.scenarios import list_scenarios, run_scenario, to_paper_markdown

router = APIRouter(tags=["scenarios"])


@router.get("/scenarios")
def get_scenarios() -> list[dict]:
    return list_scenarios()


@router.post("/scenarios/{scenario_id}/run")
def run(scenario_id: str, scope: str = "PORTFOLIO#2026-Q1", format: str = "json") -> dict:
    """Run a scenario. With format=markdown, also returns paper-ready Markdown."""
    try:
        trace = run_scenario(scenario_id, scope)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    if format == "markdown":
        trace["paper_markdown"] = to_paper_markdown(trace)
    return trace
