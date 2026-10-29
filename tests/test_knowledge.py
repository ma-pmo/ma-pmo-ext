"""A7 local RAG retrieval + A6/A7 smoke tests."""
from __future__ import annotations

from sqlalchemy import select

from ma_pmo.agents.governance import GovernanceAgent
from ma_pmo.agents.knowledge import KnowledgeAgent
from ma_pmo.connectors.vectordb import LocalLexicalStore
from ma_pmo.core.schemas.payloads.knowledge_v1 import Citation, KnowledgeV1
from ma_pmo.db.models import KpiEvent
from ma_pmo.db.session import get_session


def test_lexical_search_ranks_relevant_lesson():
    hits = LocalLexicalStore().similarity_search("data migration delay", k=3)
    assert hits, "expected search results"
    # the migration-delay lesson (LL-2024-01) must rank first
    assert hits[0]["source_id"] == "LL-2024-01"
    assert hits[0]["similarity"] > 0
    # sorted by similarity, descending
    sims = [h["similarity"] for h in hits]
    assert sims == sorted(sims, reverse=True)


def test_retrieve_returns_citations_without_llm():
    # retrieve works without an LLM (no API key needed)
    hits = KnowledgeAgent().retrieve("payment API estimate", k=2)
    assert any(h["source_id"] == "LL-2024-02" for h in hits)


def test_a7_ask_enforces_citations(monkeypatch):
    # citations are backfilled from retrieval even if the LLM omits them
    def _fake(system, user, schema, *, agent="?", model=None):
        return KnowledgeV1(
            query="", answer="Past lessons say a buffer is needed.", similar_cases=[], citations=[]
        )

    monkeypatch.setattr("ma_pmo.core.llm.complete_structured", _fake)
    result = KnowledgeAgent().ask("payment API estimate evidence", k=2)
    assert result.citations, "citations must be backfilled (hallucination control)"
    assert isinstance(result.citations[0], Citation)


def test_a6_governance_records_gate_kpi():
    result = GovernanceAgent().run({"task_ref": "PORTFOLIO#2026-Q1", "gate": "G2-planning"})
    assert result["outputs"], "gate review output"
    assert all(o["schema"] == "gate_review.v1" for o in result["outputs"])
    with get_session() as s:
        kpis = s.scalars(select(KpiEvent).where(KpiEvent.metric == "gate_review")).all()
        assert kpis, "gate KPI (delivery axis) recorded"
