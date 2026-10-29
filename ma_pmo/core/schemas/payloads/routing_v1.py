"""A1 orchestrator routing decision — routing.v1."""
from __future__ import annotations

from pydantic import BaseModel, Field

# workers that can be delegated to (excluding A1)
WORKER_AGENTS = {"A2", "A3", "A4", "A5", "A6", "A7"}


class RoutingDecision(BaseModel):
    agent: str = Field(description="worker ID to delegate to (A2–A7)")
    task: str = Field(description="description of the task delegated to that worker")


class RoutingV1(BaseModel):
    """A1's decomposition of the goal into worker delegations.

    `finish=True` ends after synthesis.
    """

    reasoning: str
    delegations: list[RoutingDecision] = Field(default_factory=list)
    finish: bool = False
