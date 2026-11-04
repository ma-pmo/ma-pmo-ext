"""A7 retrieval: offline vector search, fallback, configuration, and the labeled evaluation."""
from __future__ import annotations

import pytest

from ma_pmo.agents.knowledge import KnowledgeAgent
from ma_pmo.connectors import vectordb
from ma_pmo.connectors.vectordb import HashingEmbedder, LocalLexicalStore, VectorStore
from ma_pmo.core.config import Settings
from ma_pmo.eval.retrieval import compare, evaluate_retriever, load_queries


def test_hashing_embedder_is_deterministic_and_normalized():
    a, b = HashingEmbedder().embed(["data migration", "data migration"])
    assert a == b and abs(sum(x * x for x in a) - 1) < 1e-9


def test_vector_search_handles_korean_particles():
    q = "보고서 자동화로 시간을 줄인 경험"  # 자동화로, 시간을: particles glued to the words
    assert LocalLexicalStore().similarity_search(q) == []
    hits = VectorStore(HashingEmbedder()).similarity_search(q)
    assert hits[0]["source_id"] == "LL-2022-09"
    assert set(hits[0]) == {"source_id", "project_ref", "title", "excerpt", "similarity", "tags"}


class _Down:
    name = "down"

    def embed(self, texts):
        raise ConnectionError("embedding server unreachable")


def test_unreachable_model_falls_back_to_lexical():
    store = VectorStore(_Down())
    hits = store.similarity_search("data migration delay")
    assert hits and hits[0]["source_id"] == "LL-2024-01"
    assert evaluate_retriever(store, load_queries())["fallbacks"] == 14


def test_store_is_configurable(monkeypatch):
    monkeypatch.setattr("ma_pmo.core.config.get_settings",
                        lambda: Settings(MA_PMO_RETRIEVER="vector"))
    store = vectordb.get_store()
    assert isinstance(store, VectorStore) and isinstance(store.embedder, HashingEmbedder)
    monkeypatch.setattr("ma_pmo.core.config.get_settings",
                        lambda: Settings(MA_PMO_RETRIEVER="vector",
                                         MA_PMO_EMBEDDING_MODEL="ollama/nomic-embed-text"))
    assert vectordb.get_store().embedder.name == "ollama/nomic-embed-text"
    monkeypatch.setattr("ma_pmo.core.config.get_settings", lambda: Settings())
    assert isinstance(vectordb.get_store(), LocalLexicalStore)
    assert isinstance(KnowledgeAgent().store, LocalLexicalStore)  # default unchanged


@pytest.mark.regression
def test_labeled_retrieval_quality():
    results = compare()
    lexical, vector = results["lexical"], results["vector (char n-grams)"]
    assert lexical["n"] == vector["n"] == len(load_queries()) == 14
    assert vector["recall_at_3"] == 1.0 and vector["mrr"] > lexical["mrr"]
    assert lexical["by_kind"]["particle"] == "4/6" and vector["by_kind"]["particle"] == "6/6"


def test_metrics_on_a_toy_retriever():
    class Fixed:
        def similarity_search(self, query, k=3):
            return [{"source_id": "B"}, {"source_id": "A"}]

    queries = [{"query": "x", "relevant": ["A"], "kind": "t"},
               {"query": "y", "relevant": ["C"], "kind": "t"}]
    r = evaluate_retriever(Fixed(), queries)
    assert (r["recall_at_1"], r["recall_at_3"], r["mrr"]) == (0.0, 0.5, 0.25)
    assert r["misses"] == ["y"] and r["by_kind"] == {"t": "1/2"}
