"""The board: what earlier steps of a run published, as a step is allowed to read it.

Every message already goes to one append-only log (core/protocol.py); the board is that log seen
from one step of one run. Each step declares what it may read (`WorkflowStep.reads`):

- `isolated` (the default): nothing. The executor does not even put a `board` key in its state,
  so an agent cannot condition on its peers' findings however it is written;
- `upstream`: the posts of every step it waits for, directly or through others;
- `board`: the posts of every step in an earlier stage (`WorkflowSpec.levels`).

Publishing is the same in every mode. Separating what a step may publish from what it may read
follows ArcticSwarm's gated bulletin board (Yoon et al., 2026, arXiv:2609.01870, Section 3 and
Appendix F.1), implemented independently here. A step only ever sees steps that finished before
it could start, so a resumed run gives a step the same posts as the first attempt.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import select

from ma_pmo.core.workflow import WorkflowSpec
from ma_pmo.db.models import AgentMessageRow
from ma_pmo.db.session import get_session


def readable(spec: WorkflowSpec, step_id: str) -> set[str] | None:
    """The steps whose posts `step_id` may read; None for an isolated step."""
    step = next(s for s in spec.steps if s.id == step_id)
    if step.reads == "isolated":
        return None
    if step.reads == "upstream":
        return spec.upstream(step_id)
    levels = spec.levels()
    return {s for s, level in levels.items() if level < levels[step_id]}


def posts(run_id: str, spec: WorkflowSpec, steps: set[str] | None = None) -> list[dict[str, Any]]:
    """The posts of `steps` (every step when None) in this run, in workflow and publish order."""
    seq_of = {s.id: i for i, s in enumerate(spec.steps, start=1)}
    wanted = {seq_of[s]: s for s in (steps if steps is not None else seq_of) if s in seq_of}
    if not wanted:
        return []
    with get_session() as s:
        rows = s.scalars(select(AgentMessageRow).where(
            AgentMessageRow.run_id == run_id, AgentMessageRow.dedupe_key.is_not(None)))
        found = []
        for row in rows:
            _run, seq, _kind, n = str(row.dedupe_key).rsplit(":", 3)
            if int(seq) in wanted:
                found.append(((int(seq), int(n)), _post(row, wanted[int(seq)], int(seq))))
    return [post for _key, post in sorted(found, key=lambda f: f[0])]


def view(run_id: str, spec: WorkflowSpec, step_id: str) -> list[dict[str, Any]] | None:
    """What `step_id` may read now, or None when it is isolated."""
    steps = readable(spec, step_id)
    return None if steps is None else posts(run_id, spec, steps)


def _post(row: AgentMessageRow, step: str, seq: int) -> dict[str, Any]:
    payload = row.payload or {}
    return {"message_id": row.message_id, "step": step, "seq": seq, "agent": row.sender,
            "intent": row.intent, "task_ref": row.task_ref, "schema": payload.get("schema"),
            "data": payload.get("data", {}), "confidence": row.confidence,
            "human_gate_required": row.human_gate_required, "evidence": row.evidence or []}
