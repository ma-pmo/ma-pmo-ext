"""Knowledge store connector — A7 RAG.

Lightweight first: searches by local lexical similarity (TF cosine), with no external
vector DB or embedding API. Always returns citations to control hallucination.
Documents are indexed in every language they have (English + Korean translations), and
results are shown in the active language.

Production switch (pgvector/Qdrant):
    - add an embedding column to KnowledgeDoc and vectorize with an embedding model
    - replace similarity_search with a vector nearest-neighbor (ANN) query (same return schema)
"""
from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any

from sqlalchemy import select

from ma_pmo.core.i18n import get_lang
from ma_pmo.db.models import KnowledgeDoc
from ma_pmo.db.session import get_session

_TOKEN = re.compile(r"[0-9A-Za-z가-힣]+")


def _tokens(text: str) -> list[str]:
    return _TOKEN.findall(text.lower())


def _tf_cosine(q_tokens: list[str], d_tokens: list[str]) -> float:
    """Term-frequency cosine similarity (0–1)."""
    if not q_tokens or not d_tokens:
        return 0.0
    q, d = Counter(q_tokens), Counter(d_tokens)
    common = set(q) & set(d)
    dot = sum(q[t] * d[t] for t in common)
    if dot == 0:
        return 0.0
    nq = math.sqrt(sum(v * v for v in q.values()))
    nd = math.sqrt(sum(v * v for v in d.values()))
    return dot / (nq * nd)


class LocalLexicalStore:
    """Lexical similarity search over the lessons-learned corpus loaded in knowledge_doc."""

    def similarity_search(self, query: str, k: int = 3) -> list[dict]:
        q_tokens = _tokens(query)
        with get_session() as s:
            docs = s.scalars(select(KnowledgeDoc)).all()
            scored: list[dict[str, Any]] = []
            lang = get_lang()
            for doc in docs:
                variants = [(doc.title, doc.text), *(
                    (v.get("title", ""), v.get("text", ""))
                    for v in (doc.translations or {}).values()
                )]
                tags = " ".join(doc.tags)
                score = max(
                    _tf_cosine(q_tokens, _tokens(f"{title} {text} {tags}"))
                    for title, text in variants
                )
                if score > 0:
                    local = (doc.translations or {}).get(lang) or {}
                    title = local.get("title") or doc.title
                    text = local.get("text") or doc.text
                    scored.append(
                        {
                            "source_id": doc.id,
                            "project_ref": doc.project_ref,
                            "title": title,
                            "excerpt": text[:180],
                            "similarity": round(score, 4),
                            "tags": doc.tags,
                        }
                    )
        scored.sort(key=lambda x: x["similarity"], reverse=True)
        return scored[:k]


# default store (swap only this factory when moving to production)
def get_store() -> LocalLexicalStore:
    return LocalLexicalStore()
