"""Lessons learned on the board: what A7 found, as evidence another agent can cite.

A7 posts knowledge.v1 answers with citations. A step that the workflow lets read them (`reads`)
cites the lessons behind its own output: a message reference to A7's answer and a `knowledge`
reference per cited lesson. The lessons do not change a deterministic result (a CPM schedule, a
gate decision); they are recorded with it, so a person can see what was known when it was made,
and an experiment can measure whether removing A7 changes what other agents rest on.
"""
from __future__ import annotations

from ma_pmo.core.schemas.message import EvidenceRef
from ma_pmo.core.state.blackboard import PortfolioState


def on_board(state: PortfolioState) -> list[dict]:
    """knowledge.v1 posts this step may read; empty when it is isolated."""
    return [p for p in state.get("board", []) if p["schema"] == "knowledge.v1"]


def lesson_ids(posts: list[dict]) -> list[str]:
    """The cited lessons, in order of first appearance."""
    seen: list[str] = []
    for post in posts:
        for c in post["data"].get("citations", []):
            if c.get("source_id") and c["source_id"] not in seen:
                seen.append(c["source_id"])
    return seen


def evidence(posts: list[dict]) -> list[EvidenceRef]:
    """A reference to each A7 answer and to each lesson it cites."""
    refs = [EvidenceRef(kind="message", ref=p["message_id"]) for p in posts]
    return refs + [EvidenceRef(kind="knowledge", ref=lid) for lid in lesson_ids(posts)]
