"""A2 planning · A3 resources — deterministic, so they run without an API key.

POST /plan       : compute the portfolio CPM schedule (A2)
POST /allocate   : run resource allocation (A3)
GET  /allocations: list persisted allocations
"""
from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import select

from ma_pmo.agents.planning import PlanningAgent
from ma_pmo.agents.resource import ResourceAgent
from ma_pmo.db.models import Allocation
from ma_pmo.db.session import get_session

router = APIRouter(tags=["planning"])

_SCOPE = "PORTFOLIO#2026-Q1"


@router.post("/plan")
def run_plan(scope: str = _SCOPE) -> dict:
    """A2: CPM critical path and projected finish (records SPI/slippage KPIs)."""
    agent = PlanningAgent()
    status = agent.tracker.get_portfolio_status(scope)
    schedules = [
        agent.plan_project(p["project_id"], scope) for p in status.get("projects", [])
    ]
    return {"scope": scope, "schedules": schedules}


@router.post("/allocate")
def run_allocate(scope: str = _SCOPE) -> dict:
    """A3: run resource allocation (records utilization/idle KPIs)."""
    return ResourceAgent().allocate_portfolio(scope)


@router.get("/allocations")
def list_allocations(project_id: str | None = None, limit: int = 500) -> list[dict]:
    with get_session() as s:
        stmt = select(Allocation).limit(limit)
        if project_id:
            stmt = stmt.where(Allocation.project_id == project_id)
        rows = s.scalars(stmt).all()
        return [
            {
                "project_id": r.project_id,
                "resource_id": r.resource_id,
                "week": r.week,
                "hours": r.hours,
            }
            for r in rows
        ]
