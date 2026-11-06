"""Example agent plugin: what the remaining work of each project will cost.

Uses only `ma_pmo.sdk`. A project over the limit goes to a person, like any high-risk decision.
"""
from __future__ import annotations

import os

from pydantic import BaseModel

from ma_pmo.sdk import AgentSpec, BaseAgent, PortfolioState, get_tracker, publish

SCHEMA = "acme_budget.v1"


class BudgetV1(BaseModel):
    project_id: str
    remaining_hours: float
    remaining_cost: float
    over_limit: bool


class BudgetAgent(BaseAgent[BudgetV1]):
    agent_id = "acme.budget"
    function = "Budget"
    output_schema = BudgetV1

    def __init__(self) -> None:
        self.rate = float(os.environ.get("ACME_HOURLY_RATE", "100"))
        self.limit = float(os.environ.get("ACME_PROJECT_LIMIT", "30000"))

    def run(self, state: PortfolioState) -> dict:
        scope = state.get("task_ref", "PORTFOLIO#2026-Q1")
        outputs = []
        for project in get_tracker().get_portfolio_status(scope).get("projects", []):
            hours = sum(t["effort"] * (1 - t["percent_complete"] / 100) for t in project["tasks"])
            cost = round(hours * self.rate, 2)
            over = cost > self.limit
            budget = BudgetV1(project_id=project["project_id"], remaining_hours=round(hours, 1),
                              remaining_cost=cost, over_limit=over)
            outputs.append(publish(self, SCHEMA, budget, needs_approval=over,
                                   task_ref=f"{scope}/{project['project_id']}"))
        return {"outputs": outputs}


SPEC = AgentSpec(
    id="acme.budget",
    name=("Budget", "예산"),
    version="0.1.0",
    capability="Budget (cost of remaining work): budget, cost, spend",
    keywords=("budget", "cost", "spend", "예산", "비용"),
    default_task=("Estimate the cost of remaining work", "남은 작업 비용 추정"),
    output_schema=SCHEMA,
    factory=BudgetAgent,
    payload=BudgetV1,
)
