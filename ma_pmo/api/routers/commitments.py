"""Commitments (roadmap 9): what decisions oblige whom to do, by when, and the operations on them.

GET  /commitments                  : filter by state, debtor, project
GET  /commitments/{id}             : one, with its history
POST /commitments/{id}/{op}        : detach | discharge | cancel | release | delegate | assign
POST /commitments/check            : discharge the gate conditions the tracker shows are met
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from ma_pmo.api.auth import ANONYMOUS, CurrentPrincipal
from ma_pmo.core import commitments

router = APIRouter(tags=["commitments"])
OPS = {"detach", "discharge", "cancel", "release", "delegate", "assign"}


class Operation(BaseModel):
    # ignored when auth is on: the authenticated user is recorded instead
    by: str = ""
    note: str = ""
    to: str | None = None  # delegate: the new debtor; assign: the new creditor
    reference: str | None = None  # discharge: what shows it is done (a ticket, a link)


@router.get("/commitments")
def list_commitments(state: str | None = None, debtor: str | None = None,
                     project: str | None = None,
                     limit: int = Query(200, ge=1, le=1000)) -> list[dict]:
    return commitments.list_open(state=state, debtor=debtor, project=project, limit=limit)


@router.post("/commitments/check")
def check_commitments() -> dict:
    done = commitments.check_tracker()
    return {"discharged": [c["id"] for c in done]}


@router.get("/commitments/{commitment_id}")
def get_commitment(commitment_id: str) -> dict:
    found = commitments.get(commitment_id)
    if found is None:  # also one in another workspace
        raise HTTPException(status_code=404, detail=f"commitment {commitment_id} not found")
    return found


@router.post("/commitments/{commitment_id}/{op}")
def operate(commitment_id: str, op: str, body: Operation, principal: CurrentPrincipal) -> dict:
    if op not in OPS:
        raise HTTPException(status_code=404, detail=f"unknown operation: {op}")
    by = principal.subject if principal is not ANONYMOUS else (body.by or "anonymous")
    evidence = [{"kind": "reference", "ref": body.reference}] if body.reference else None
    try:
        return commitments.apply(commitment_id, op, by=by, note=body.note, to=body.to,
                                 evidence=evidence)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=f"commitment {e.args[0]} not found") from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
