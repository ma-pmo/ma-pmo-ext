"""BaseAgent — role prompt + output schema + run().

Each agent is defined by a role prompt + tool set + output schema (JSON), and its
output is always validated against a Pydantic schema (§3.2, hallucination control).
"""
from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel

from ma_pmo.core import llm
from ma_pmo.core.state.blackboard import PortfolioState

TOutput = TypeVar("TOutput", bound=BaseModel)


class BaseAgent(Generic[TOutput]):
    #: agent ID (e.g. "A5")
    agent_id: str = "A?"
    #: PMO function name
    function: str = ""
    #: role prompt (system)
    role_prompt: str = ""
    #: output schema (Pydantic)
    output_schema: type[TOutput]

    def structured(self, user_prompt: str) -> TOutput:
        """Call the LLM and return output validated against output_schema."""
        return llm.complete_structured(
            self.role_prompt, user_prompt, self.output_schema, agent=self.agent_id
        )

    def run(self, state: PortfolioState) -> dict:
        """LangGraph node entry point; implemented by subclasses.

        Returns a partial PortfolioState update (dict).
        """
        raise NotImplementedError
