"""commitment.v1: one operation on a commitment, posted in the conversation it came from."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

Op = Literal["create", "detach", "discharge", "cancel", "release", "delegate", "assign",
             "violate", "expire", "escalate"]


class CommitmentV1(BaseModel):
    commitment_id: str
    op: Op
    state: str  # the state after the operation
    debtor: str
    creditor: str
    consequent: str
    due: str | None = None
    project_id: str | None = None
    by: str
    note: str = ""
