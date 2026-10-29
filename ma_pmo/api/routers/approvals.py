"""HITL approval queue — GET pending items · POST approve/reject (§8)."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ma_pmo.core import hitl

router = APIRouter(tags=["approvals"])


class ApprovalDecision(BaseModel):
    approver: str
    decision: str  # approve | reject


@router.get("/approvals")
def list_approvals() -> list[dict]:
    return hitl.list_pending()


@router.post("/approvals/{approval_id}")
def resolve_approval(approval_id: int, body: ApprovalDecision) -> dict:
    try:
        return hitl.resolve(
            approval_id, approver=body.approver, decision=body.decision
        )
    except (KeyError, ValueError) as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
