"""A7 Knowledge agent — knowledge/lessons learned (RAG) (§3.2). [operational]

Flow: local lexical similarity search (deterministic, no key) -> citations ->
      optional LLM synthesis -> KnowledgeV1 (citations enforced) -> message to A1.

retrieve() works without an API key; only answer synthesis (ask) uses the LLM.
"""
from __future__ import annotations

import json
import re

from ma_pmo.agents import common
from ma_pmo.agents.base import BaseAgent
from ma_pmo.connectors.vectordb import Retriever, get_store
from ma_pmo.core import protocol, tracing
from ma_pmo.core.i18n import tr
from ma_pmo.core.obs import get_logger
from ma_pmo.core.schemas.message import AgentMessage, Intent, MessagePayload
from ma_pmo.core.schemas.payloads.knowledge_v1 import Citation, KnowledgeV1
from ma_pmo.core.scope import DEFAULT_SCOPE
from ma_pmo.core.state.blackboard import PortfolioState

_log = get_logger("knowledge")

_ROLE = """You are the PMO knowledge agent. Answer only from the retrieved lessons learned
(citations) below. Do not invent anything not in the evidence, and cite a source_id for
each claim (hallucination control)."""


class KnowledgeAgent(BaseAgent[KnowledgeV1]):
    agent_id = "A7"
    function = "Knowledge (RAG/similar cases)"
    role_prompt = _ROLE
    output_schema = KnowledgeV1

    def __init__(self, store: Retriever | None = None) -> None:
        self.store = store if store is not None else get_store()

    # ── retrieval only (deterministic, no key) ─────────────────────
    def retrieve(self, query: str, k: int = 3) -> list[dict]:
        return self.store.similarity_search(query, k=k)

    # ── retrieval + LLM synthesis -> KnowledgeV1 ───────────────────
    def ask(self, query: str, k: int = 3) -> KnowledgeV1:
        hits = self.retrieve(query, k=k)
        citations = [
            Citation(source_id=h["source_id"], excerpt=h["excerpt"], similarity=h["similarity"])
            for h in hits
        ]
        if not hits:
            return KnowledgeV1(
                query=query,
                answer=tr(
                    "No relevant lessons learned were found.",
                    "관련 과거 교훈을 찾지 못했습니다.",
                ),
                similar_cases=[],
                citations=[],
            )

        prompt = (
            f"Question: {query}\n\nRetrieved lessons (JSON):\n"
            f"{json.dumps(hits, ensure_ascii=False, indent=2)}\n\n"
            "Answer only from the lessons above and fill similar_cases with source_ids."
        )
        try:
            result = self.structured(prompt)
        except Exception as e:  # no LLM / outage -> extractive fallback answer
            tracing.mark_fallback("A7 answer", e)
            top = hits[0]
            result = KnowledgeV1(
                query=query,
                answer=f"[{top['source_id']}] {top['title']}: {top['excerpt']}",
                similar_cases=[h["source_id"] for h in hits],
                citations=citations,
            )
        result = _grounded(result, hits, citations)
        result.query = query
        return result

    def run(self, state: PortfolioState) -> dict:
        query = state.get("goal", "")
        scope = state.get("task_ref", DEFAULT_SCOPE)
        result = self.ask(query)

        msg = AgentMessage(
            sender=self.agent_id,
            receiver="A1",
            intent=Intent.INFORM,
            task_ref=scope,
            payload=MessagePayload(schema_="knowledge.v1", data=result.model_dump()),
            confidence=0.85,
        )
        protocol.publish(msg)
        return {
            "outputs": [common.entry(self.agent_id, "knowledge.v1", result)],
            "messages": [common.wire(msg)],
        }


def _grounded(result: KnowledgeV1, hits: list[dict], retrieved: list[Citation]) -> KnowledgeV1:
    """Keep only what the retrieved lessons support.

    A citation the model makes up (a source_id that was not retrieved) is dropped, and the
    excerpt of a kept one is the lesson's own text, not the model's paraphrase. If the answer
    itself names a lesson that was not retrieved, the answer is not trusted and the extractive
    answer replaces it. With nothing left, the retrieved lessons are cited.
    """
    known = {c.source_id: c for c in retrieved}
    # lesson ids the answer names, e.g. [LL-2024-01]
    named = set(re.findall(r"\[([A-Za-z]+-[\w.-]+)\]", result.answer))
    made_up = sorted({c.source_id for c in result.citations if c.source_id not in known}
                     | {sid for sid in named if sid not in known})
    if made_up:
        _log.warning("knowledge_uncited_sources", sources=made_up)
    if named - set(known):
        top = hits[0]
        result.answer = f"[{top['source_id']}] {top['title']}: {top['excerpt']}"
    kept = [known[c.source_id] for c in result.citations if c.source_id in known]
    result.citations = list({c.source_id: c for c in kept}.values()) or retrieved
    result.similar_cases = [sid for sid in result.similar_cases if sid in known] or list(known)
    return result
