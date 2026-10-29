"""A6 governance · A7 knowledge endpoints.

POST /gate-review        : gate review (A6, deterministic — no key needed)
GET  /knowledge/search   : lessons-learned search (A7 retrieval, deterministic — no key needed)
POST /knowledge/ask      : search + LLM synthesis (A7, needs an LLM)
"""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from ma_pmo.agents.governance import GovernanceAgent
from ma_pmo.agents.knowledge import KnowledgeAgent

router = APIRouter(tags=["governance-knowledge"])

_SCOPE = "PORTFOLIO#2026-Q1"


@router.post("/gate-review")
def gate_review(gate: str = "G2-planning", scope: str = _SCOPE) -> dict:
    """A6: gate review for every project in the portfolio (records gate KPIs)."""
    agent = GovernanceAgent()
    status = agent.tracker.get_portfolio_status(scope)
    reviews = [
        agent.review_project(p["project_id"], gate, scope)
        for p in status.get("projects", [])
    ]
    return {"scope": scope, "gate": gate, "reviews": reviews}


@router.get("/knowledge/search")
def knowledge_search(q: str, k: int = 3) -> dict:
    """A7 retrieval only — returns citations. No LLM (no key needed)."""
    return {"query": q, "citations": KnowledgeAgent().retrieve(q, k=k)}


class AskRequest(BaseModel):
    query: str
    k: int = 3


@router.post("/knowledge/ask")
def knowledge_ask(req: AskRequest) -> dict:
    """A7 retrieval + LLM synthesis (needs an LLM)."""
    return KnowledgeAgent().ask(req.query, k=req.k).model_dump()
