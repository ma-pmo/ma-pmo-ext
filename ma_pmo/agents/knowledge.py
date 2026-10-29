"""A7 Knowledge agent — knowledge/lessons learned (RAG) (§3.2). [operational]

Flow: local lexical similarity search (deterministic, no key) -> citations ->
      optional LLM synthesis -> KnowledgeV1 (citations enforced) -> message to A1.

retrieve() works without an API key; only answer synthesis (ask) uses the LLM.
"""
from __future__ import annotations

import json

from ma_pmo.agents.base import BaseAgent
from ma_pmo.connectors.vectordb import LocalLexicalStore
from ma_pmo.core import protocol
from ma_pmo.core.i18n import tr
from ma_pmo.core.schemas.message import AgentMessage, Intent, MessagePayload
from ma_pmo.core.schemas.payloads.knowledge_v1 import Citation, KnowledgeV1
from ma_pmo.core.state.blackboard import PortfolioState

_ROLE = """You are the PMO knowledge agent. Answer only from the retrieved lessons learned
(citations) below. Do not invent anything not in the evidence, and cite a source_id for
each claim (hallucination control)."""


class KnowledgeAgent(BaseAgent[KnowledgeV1]):
    agent_id = "A7"
    function = "Knowledge (RAG/similar cases)"
    role_prompt = _ROLE
    output_schema = KnowledgeV1

    def __init__(self, store: LocalLexicalStore | None = None) -> None:
        self.store = store or LocalLexicalStore()

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
        except Exception:  # no LLM / outage -> extractive fallback answer
            top = hits[0]
            result = KnowledgeV1(
                query=query,
                answer=f"[{top['source_id']}] {top['title']}: {top['excerpt']}",
                similar_cases=[h["source_id"] for h in hits],
                citations=citations,
            )
        # enforce citations: backfill from retrieval if the LLM omitted them
        if not result.citations:
            result.citations = citations
        result.query = query
        return result

    def run(self, state: PortfolioState) -> dict:
        query = state.get("goal", "")
        scope = state.get("task_ref", "PORTFOLIO#2026-Q1")
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
            "outputs": [
                {"agent": self.agent_id, "schema": "knowledge.v1", "data": result.model_dump()}
            ],
            "messages": [msg.model_dump(by_alias=True, mode="json")],
        }
