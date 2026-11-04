"""HITL approval queue — GET pending items · POST approve/reject (§8)."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ma_pmo.api.auth import ANONYMOUS, CurrentPrincipal
from ma_pmo.core import hitl

router = APIRouter(tags=["approvals"])


class ApprovalDecision(BaseModel):
    # ignored when auth is on: the authenticated user is recorded instead
    approver: str = ""
    decision: str  # approve | reject


@router.get("/approvals")
def list_approvals() -> list[dict]:
    return hitl.list_pending()


@router.post("/approvals/{approval_id}")
def resolve_approval(approval_id: int, body: ApprovalDecision, principal: CurrentPrincipal) -> dict:
    # With auth on, a caller cannot sign a decision in someone else's name.
    approver = principal.subject if principal is not ANONYMOUS else (body.approver or "anonymous")
    try:
        return hitl.resolve(approval_id, approver=approver, decision=body.decision)
    except (KeyError, ValueError) as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
