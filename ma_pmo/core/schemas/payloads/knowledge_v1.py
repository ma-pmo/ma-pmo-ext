"""A7 knowledge output — knowledge.v1 (RAG citations enforced)."""
from __future__ import annotations

from pydantic import BaseModel, Field


class Citation(BaseModel):
    source_id: str
    excerpt: str
    similarity: float | None = None


class KnowledgeV1(BaseModel):
    query: str
    answer: str
    similar_cases: list[str] = Field(default_factory=list)
    citations: list[Citation] = Field(
        default_factory=list, description="citations are mandatory (hallucination control)"
    )
