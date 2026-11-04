"""Knowledge store connector — A7 RAG. Always returns citations to control hallucination.

Two retrievers share one interface, `similarity_search(query, k) -> list[hit]`:

- `LocalLexicalStore` (default) — term-frequency cosine over whole words. No dependencies.
- `VectorStore` — cosine over embeddings, picked with `MA_PMO_RETRIEVER=vector`:
    - `MA_PMO_EMBEDDING_MODEL` empty → `HashingEmbedder`: character n-grams hashed into a fixed
      vector. Offline and deterministic; matches inflections and Korean words with particles
      attached ("마이그레이션이" ↔ "마이그레이션"), which whole-word search misses.
    - `MA_PMO_EMBEDDING_MODEL=<litellm model>` (e.g. `ollama/nomic-embed-text`,
      `text-embedding-3-small`) → a real embedding model that also matches synonyms. If the
      model cannot be reached, the store falls back to lexical search (logged and traced).

Documents are indexed in every language they have (English + Korean translations), and hits
are shown in the active language. Document vectors are cached in memory per document version.
For large corpora, swap `VectorStore` for pgvector/Qdrant behind the same interface.
"""
from __future__ import annotations

import hashlib
import math
import re
from collections import Counter
from collections.abc import Sequence
from typing import Any, Protocol

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


class Retriever(Protocol):
    def similarity_search(self, query: str, k: int = 3) -> list[dict]: ...


def _variants(doc: KnowledgeDoc) -> list[str]:
    """Searchable text of a document in each of its languages."""
    tags = " ".join(doc.tags)
    texts = [(doc.title, doc.text), *(
        (v.get("title", ""), v.get("text", "")) for v in (doc.translations or {}).values()
    )]
    return [f"{title} {text} {tags}" for title, text in texts]


def _hit(doc: KnowledgeDoc, score: float) -> dict[str, Any]:
    local = (doc.translations or {}).get(get_lang()) or {}
    return {
        "source_id": doc.id,
        "project_ref": doc.project_ref,
        "title": local.get("title") or doc.title,
        "excerpt": (local.get("text") or doc.text)[:180],
        "similarity": round(score, 4),
        "tags": doc.tags,
    }


def _top(scored: list[dict], k: int) -> list[dict]:
    scored.sort(key=lambda x: x["similarity"], reverse=True)
    return scored[:k]


class LocalLexicalStore:
    """Lexical similarity search over the lessons-learned corpus loaded in knowledge_doc."""

    def similarity_search(self, query: str, k: int = 3) -> list[dict]:
        q_tokens = _tokens(query)
        with get_session() as s:
            scored = []
            for doc in s.scalars(select(KnowledgeDoc)).all():
                score = max(_tf_cosine(q_tokens, _tokens(v)) for v in _variants(doc))
                if score > 0:
                    scored.append(_hit(doc, score))
        return _top(scored, k)


# ── embeddings ────────────────────────────────────────────────────────────────

class Embedder(Protocol):
    name: str

    def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


def _normalize(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(x * x for x in vec))
    return [x / norm for x in vec] if norm else vec


class HashingEmbedder:
    """Character n-grams (per word, with boundaries) hashed into `dim` buckets, log-scaled and
    L2-normalized. Offline, deterministic, language-agnostic; not semantic."""

    name = "hashing-char-ngrams"

    def __init__(self, dim: int = 1024, ngrams: tuple[int, ...] = (2, 3, 4)) -> None:
        self.dim, self.ngrams = dim, ngrams

    def _vector(self, text: str) -> list[float]:
        counts: Counter[int] = Counter()
        for word in _tokens(text):
            padded = f" {word} "
            for n in self.ngrams:
                for i in range(len(padded) - n + 1):
                    gram = padded[i:i + n]
                    digest = hashlib.md5(gram.encode(), usedforsecurity=False).digest()
                    counts[int.from_bytes(digest[:4], "little") % self.dim] += 1
        vec = [0.0] * self.dim
        for index, count in counts.items():
            vec[index] = 1.0 + math.log(count)
        return _normalize(vec)

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._vector(t) for t in texts]


class LiteLLMEmbedder:
    """Any embedding model LiteLLM supports (OpenAI, Voyage, Cohere, local Ollama, ...)."""

    def __init__(self, model: str, api_base: str = "") -> None:
        self.name, self.api_base = model, api_base

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        import litellm

        kwargs: dict[str, Any] = {"api_base": self.api_base} if self.api_base else {}
        resp = litellm.embedding(model=self.name, input=list(texts), **kwargs)
        return [_normalize(list(item["embedding"])) for item in resp.data]


def _dot(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=False))


class VectorStore:
    """Cosine similarity over embeddings of every language variant of every document."""

    def __init__(self, embedder: Embedder, *, min_score: float = 0.1,
                 fallback: Retriever | None = None) -> None:
        self.embedder = embedder
        self.min_score = min_score
        self.fallback = fallback if fallback is not None else LocalLexicalStore()
        self._cache: dict[tuple[str, str], list[list[float]]] = {}
        self.fallback_count = 0  # searches answered by the fallback (model unreachable)

    def _doc_vectors(self, doc: KnowledgeDoc) -> list[list[float]]:
        variants = _variants(doc)
        key = (doc.id, hashlib.sha256("\x1f".join(variants).encode()).hexdigest())
        if key not in self._cache:
            self._cache[key] = self.embedder.embed(variants)
        return self._cache[key]

    def similarity_search(self, query: str, k: int = 3) -> list[dict]:
        try:
            with get_session() as s:
                docs = s.scalars(select(KnowledgeDoc)).all()
                q = self.embedder.embed([query])[0]
                scored = []
                for doc in docs:
                    score = max(_dot(q, v) for v in self._doc_vectors(doc))
                    if score >= self.min_score:
                        scored.append(_hit(doc, score))
            return _top(scored, k)
        except Exception as e:  # embedding model unreachable -> lexical search still answers
            from ma_pmo.core import tracing
            from ma_pmo.core.obs import get_logger

            get_logger("knowledge").warning("embedding_fallback", model=self.embedder.name,
                                            error=str(e)[:200])
            tracing.mark_fallback("A7 retrieval", e)
            self.fallback_count += 1
            return self.fallback.similarity_search(query, k)


def get_store() -> Retriever:
    """The configured retriever (`MA_PMO_RETRIEVER`, `MA_PMO_EMBEDDING_MODEL`)."""
    from ma_pmo.core.config import get_settings

    settings = get_settings()
    if settings.retriever.strip().lower() != "vector":
        return LocalLexicalStore()
    model = settings.embedding_model.strip()
    embedder: Embedder = (LiteLLMEmbedder(model, settings.embedding_api_base) if model
                          else HashingEmbedder())
    return VectorStore(embedder)
