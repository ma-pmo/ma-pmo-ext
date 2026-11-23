"""question.v1: an agent asks a person for a fact it needs, instead of guessing (roadmap 9)."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

AnswerType = Literal["value", "choice", "date", "yes_no"]


class QuestionV1(BaseModel):
    question_id: str  # the commitment that tracks it
    key: str  # what is asked, e.g. PROJ-77.planned_start
    ask: str
    why: str
    answer_type: AnswerType
    options: list[str] = Field(default_factory=list)  # choice only
    default: Any = None  # what the step does without an answer by `due`
    due: str | None = None
    project_id: str | None = None
