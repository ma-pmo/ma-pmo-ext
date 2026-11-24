"""Policy and the guardrail log (roadmap 10). Changing the policy needs `admin`.

GET /policy              : the policy in force, every guardrail with its point, mode and params
GET /policy/versions     : every version, newest first
PUT /policy              : a new version {guardrails: {name: {mode, params}}, note}
GET /guardrails          : recorded results (?name=, ?point=, ?decision=, ?outcome=, ?run=)
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from ma_pmo.api.auth import ANONYMOUS, CurrentPrincipal
from ma_pmo.core import guardrails, policy

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


@router.get("/guardrails")
def guardrail_log(name: str | None = None, point: str | None = None,
                  decision: str | None = None, outcome: str | None = None,
                  run: str | None = None, limit: int = Query(200, ge=1, le=1000)) -> list[dict]:
    return guardrails.log(name=name, point=point, decision=decision, outcome=outcome, run=run,
                          limit=limit)
