"""Review verdicts — review.v1: one constraint of one post, verified or challenged with evidence.

A reviewer posts one verdict per constraint instead of accepting or rejecting a whole output, so
what is missing can be asked for precisely. `builder` reviews come from the agent that made the
output (or the one that consumes it) checking it against what other steps published; `dedicated`
reviews come from a reviewer with no task of its own. The three verdicts and the split between
the two reviewer roles follow ArcticSwarm (Yoon et al., 2026, arXiv:2609.01870, Section 3 and
Appendix G.1), implemented independently.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

from ma_pmo.core.schemas.message import EvidenceRef

VERIFIED, CHALLENGE, ALTERNATIVE = "VERIFIED", "CHALLENGE", "ALTERNATIVE"


class ReviewV1(BaseModel):
    target: str = Field(min_length=1)  # message_id of the post under review
    constraint: str = Field(min_length=1)  # e.g. gate.no_open_high_risk
    project_id: str | None = None
    verdict: Literal["VERIFIED", "CHALLENGE", "ALTERNATIVE"]
    role: Literal["builder", "dedicated"]
    evidence: list[EvidenceRef] = Field(default_factory=list)
    rationale: str = ""
    alternative: dict | None = None  # ALTERNATIVE: what else could be decided, and why

    @model_validator(mode="after")
    def _grounded(self) -> ReviewV1:
        if self.verdict in (VERIFIED, CHALLENGE) and not self.evidence:
            raise ValueError(f"a {self.verdict} verdict must cite its evidence")
        if self.verdict == ALTERNATIVE and not self.alternative:
            raise ValueError("an ALTERNATIVE verdict must describe the alternative")
        return self
