"""Questions agents asked people (roadmap 9): what is waiting for an answer, and answering it.

GET  /questions                    : open questions, soonest due first (?run= for one run)
POST /questions/{id}/answer        : answer one; the run resumes once nothing else is open
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ma_pmo.api.auth import ANONYMOUS, CurrentPrincipal
from ma_pmo.core import questions

router = APIRouter(tags=["questions"])


class Answer(BaseModel):
    # ignored when auth is on: the authenticated user is recorded instead
    by: str = ""
    value: Any


@router.get("/questions")
def list_questions(run: str | None = None) -> list[dict]:
    return questions.list_open(run)


@router.post("/questions/{question_id}/answer")
def answer_question(question_id: str, body: Answer, principal: CurrentPrincipal) -> dict:
    by = principal.subject if principal is not ANONYMOUS else (body.by or "anonymous")
    try:
        return questions.answer(question_id, body.value, by=by)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=f"question {e.args[0]} not found") from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
