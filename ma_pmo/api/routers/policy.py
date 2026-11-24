"""Policy and the guardrail log (roadmap 10). Changing the policy needs `admin`.

GET /policy              : the policy in force, every guardrail with its point, mode and params
GET /policy/versions     : every version, newest first
PUT /policy              : a new version {guardrails: {name: {mode, params}}, note}
GET /guardrails          : recorded results (?name=, ?point=, ?decision=, ?outcome=, ?run=)
GET /tolerances          : the limits per level, and in force for ?project= (in ?portfolio=)
PUT /tolerances          : replace them {tolerances: {workspace, portfolios, projects}, note}
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from ma_pmo.api.auth import ANONYMOUS, CurrentPrincipal
from ma_pmo.core import guardrails, policy, tolerances

router = APIRouter(tags=["policy"])


class PolicyChange(BaseModel):
    guardrails: dict[str, dict[str, Any]]
    note: str = ""


@router.get("/policy")
def get_policy() -> dict:
    return policy.current()


@router.get("/policy/versions")
def policy_versions() -> list[dict]:
    return policy.versions()


@router.put("/policy")
def change_policy(body: PolicyChange, principal: CurrentPrincipal) -> dict:
    by = principal.subject if principal is not ANONYMOUS else "anonymous"
    try:
        return policy.change(body.guardrails, by=by, note=body.note)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


class ToleranceChange(BaseModel):
    tolerances: dict[str, Any]
    note: str = ""


@router.get("/tolerances")
def get_tolerances(project: str | None = None, portfolio: str | None = None) -> dict:
    return {"levels": tolerances.document(), "limits": list(tolerances.LIMITS),
            "effective": tolerances.effective(project, portfolio) if project or portfolio
            else None}


@router.put("/tolerances")
def change_tolerances(body: ToleranceChange, principal: CurrentPrincipal) -> dict:
    by = principal.subject if principal is not ANONYMOUS else "anonymous"
    try:
        return policy.change({}, by=by, note=body.note, tolerances=body.tolerances)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/guardrails")
def guardrail_log(name: str | None = None, point: str | None = None,
                  decision: str | None = None, outcome: str | None = None,
                  run: str | None = None, limit: int = Query(200, ge=1, le=1000)) -> list[dict]:
    return guardrails.log(name=name, point=point, decision=decision, outcome=outcome, run=run,
                          limit=limit)
