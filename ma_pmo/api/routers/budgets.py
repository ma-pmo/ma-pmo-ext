"""Budgets (see core/budgets.py).

GET /budgets         : each budget and what has been spent against it this month
PUT /budgets/{kind}  : set the warning and hard limit of `month` or `run` (admin); both null
                       removes it
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ma_pmo.api.auth import CurrentPrincipal
from ma_pmo.core import budgets

router = APIRouter(tags=["budgets"])


class Limits(BaseModel):
    warn_usd: float | None = None
    limit_usd: float | None = None


@router.get("/budgets")
def get_budgets() -> dict:
    return budgets.status()


@router.put("/budgets/{kind}")
def put_budget(kind: str, body: Limits, principal: CurrentPrincipal) -> dict:
    try:
        return budgets.set_budget(kind, body.warn_usd, body.limit_usd, principal.subject)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from None
