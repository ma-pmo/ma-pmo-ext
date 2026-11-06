"""A1 orchestrator routing decision — routing.v1."""
from __future__ import annotations

from pydantic import BaseModel, Field


class RoutingDecision(BaseModel):
    agent: str = Field(description="worker ID to delegate to")
    task: str = Field(description="description of the task delegated to that worker")


class RoutingV1(BaseModel):
    """A1's decomposition of the goal into worker delegations.

    `finish=True` ends after synthesis.
    """

    reasoning: str
    delegations: list[RoutingDecision] = Field(default_factory=list)
    finish: bool = False
