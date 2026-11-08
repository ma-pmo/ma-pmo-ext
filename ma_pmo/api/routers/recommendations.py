"""Model-tier recommendations from replays (see core/replay.py).

POST /recommendations/replay            : replay a step on the fast model (operator)
GET  /recommendations                   : every recommendation, newest first
POST /recommendations/{id}/approve      : make a draft with the change (approver, admin)
POST /recommendations/{id}/reject       : decline it (approver, admin)
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ma_pmo.api.auth import CurrentPrincipal
from ma_pmo.core import replay
from ma_pmo.core.i18n import tr

router = APIRouter(tags=["recommendations"])


class Replay(BaseModel):
    workflow_id: str
    step_id: str
    repeat: int = 3
    tolerance: float = 0.05


def _unknown(what: object) -> HTTPException:
    return HTTPException(status_code=404, detail=tr(f"not found: {what}", f"없습니다: {what}"))


@router.post("/recommendations/replay", status_code=201)
def run_replay(body: Replay, principal: CurrentPrincipal) -> dict:
    try:
        return replay.replay(body.workflow_id, body.step_id, repeat=body.repeat,
                             tolerance=body.tolerance, by=principal.subject)
    except KeyError:
        raise _unknown(f"{body.workflow_id}/{body.step_id}") from None
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from None


@router.get("/recommendations")
def list_recommendations() -> list[dict]:
    return replay.recommendations()


def _decide(rec_id: int, decision: str, who: str) -> dict:
    try:
        return replay.decide(rec_id, decision, who)
    except KeyError:
        raise _unknown(rec_id) from None
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from None


@router.post("/recommendations/{rec_id}/approve")
def approve(rec_id: int, principal: CurrentPrincipal) -> dict:
    return _decide(rec_id, replay.APPROVED, principal.subject)


@router.post("/recommendations/{rec_id}/reject")
def reject(rec_id: int, principal: CurrentPrincipal) -> dict:
    return _decide(rec_id, replay.REJECTED, principal.subject)
