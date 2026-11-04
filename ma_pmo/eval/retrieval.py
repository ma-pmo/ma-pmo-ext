"""Retrieval quality of A7 on a labeled query set — recall@k and MRR, per retriever.

    ma-pmo eval --retrieval

The query set (`fixtures/retrieval_eval.json`) is paraphrased on purpose: inflections, Korean
particles and synonyms, so the numbers say how well A7 finds a lesson when people do not use
the lesson's exact words. Results are broken down by query kind.
"""
from __future__ import annotations

import json
from pathlib import Path

from ma_pmo.connectors.vectordb import HashingEmbedder, LocalLexicalStore, Retriever, VectorStore

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "retrieval_eval.json"


def load_queries(path: str | Path = FIXTURE) -> list[dict]:
    return json.loads(Path(path).read_text(encoding="utf-8"))["queries"]


def evaluate_retriever(store: Retriever, queries: list[dict], k: int = 3) -> dict:
    fallbacks_before = getattr(store, "fallback_count", 0)
    hits_at_1 = hits_at_k = 0
    reciprocal = 0.0
    by_kind: dict[str, list[int]] = {}
    misses = []
    for q in queries:
        ranked = [h["source_id"] for h in store.similarity_search(q["query"], k=k)]
        rank = next((i + 1 for i, sid in enumerate(ranked) if sid in q["relevant"]), None)
        hits_at_1 += rank == 1
        hits_at_k += rank is not None
        reciprocal += 1 / rank if rank else 0.0
        stats = by_kind.setdefault(q["kind"], [0, 0])
        stats[0] += rank is not None
        stats[1] += 1
        if rank is None:
            misses.append(q["query"])
    n = len(queries) or 1
    return {
        "n": len(queries),
        "recall_at_1": round(hits_at_1 / n, 3),
        f"recall_at_{k}": round(hits_at_k / n, 3),
        "mrr": round(reciprocal / n, 3),
        "by_kind": {kind: f"{found}/{total}" for kind, (found, total) in sorted(by_kind.items())},
        "misses": misses,
        # >0 means the embedding model was unreachable and lexical search answered instead
        "fallbacks": getattr(store, "fallback_count", 0) - fallbacks_before,
    }


def compare(k: int = 3, extra: dict[str, Retriever] | None = None) -> dict[str, dict]:
    """Lexical vs. offline vector search (plus any configured retrievers)."""
    queries = load_queries()
    stores: dict[str, Retriever] = {
        "lexical": LocalLexicalStore(),
        "vector (char n-grams)": VectorStore(HashingEmbedder()),
        **(extra or {}),
    }
    return {name: evaluate_retriever(store, queries, k) for name, store in stores.items()}
