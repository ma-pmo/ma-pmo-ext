"""Roles (RACI) per decision kind and project (roadmap 9). Changing them needs `admin`.

GET    /roles                      : every assignment (?kind=, ?project=)
GET    /roles/who?kind=&project=   : the R, A, C and I for one decision, as they resolve
POST   /roles                      : assign {kind, role, person, project}
DELETE /roles/{id}                 : remove one
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ma_pmo.api.auth import ANONYMOUS, CurrentPrincipal
from ma_pmo.core import roles

router = APIRouter(tags=["roles"])


class Assignment(BaseModel):
    kind: str  # gate, budget, allocation, question, ..., or * for every kind
    role: str  # R | A | C | I
    person: str
    project: str | None = None  # empty: every project


@router.get("/roles")
def list_roles(kind: str | None = None, project: str | None = None) -> list[dict]:
    return roles.list_roles(kind, project)


@router.get("/roles/who")
def who(kind: str, project: str | None = None) -> dict:
    return roles.raci(kind, project)


@router.post("/roles")
def assign(body: Assignment, principal: CurrentPrincipal) -> dict:
    by = principal.subject if principal is not ANONYMOUS else "anonymous"
    try:
        return roles.assign(body.kind, body.role, body.person, project=body.project, by=by)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.delete("/roles/{assignment_id}")
def remove(assignment_id: int) -> dict:
    if not roles.remove(assignment_id):  # also one in another workspace
        raise HTTPException(status_code=404, detail=f"role assignment {assignment_id} not found")
    return {"removed": assignment_id}
