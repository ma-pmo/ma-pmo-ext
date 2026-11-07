"""Where the caller can work: the workspaces they can enter and the portfolios in one.

GET /workspaces : the caller's workspaces with their roles there (no X-Workspace needed)
GET /portfolios : the portfolios of the request's workspace
"""
from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import select

from ma_pmo.api.auth import CurrentPrincipal
from ma_pmo.core import workspace
from ma_pmo.core.scope import DEFAULT_SCOPE
from ma_pmo.db import workspaces
from ma_pmo.db.models import Portfolio
from ma_pmo.db.session import get_session

router = APIRouter(tags=["workspaces"])


@router.get("/workspaces")
def list_workspaces(principal: CurrentPrincipal) -> dict:
    """Only the workspaces where the caller has a role: the others stay invisible."""
    granted = workspaces.memberships_of(principal.subject)
    visible = []
    for w in workspaces.list_all():
        roles = principal.in_workspace(w["id"], granted.get(w["id"], frozenset())).roles
        if roles:
            visible.append({**w, "roles": sorted(roles)})
    return {"default": workspace.current(), "workspaces": visible}


@router.get("/portfolios")
def list_portfolios() -> dict:
    with get_session() as s:
        rows = s.scalars(select(Portfolio).order_by(Portfolio.id))
        portfolios = [{"id": p.id, "name": p.name, "period": p.period,
                       "plan_start": p.plan_start} for p in rows]
    return {"default": DEFAULT_SCOPE, "portfolios": portfolios}
