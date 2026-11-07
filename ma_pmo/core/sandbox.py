"""A throwaway workspace on the demo data, for dry runs and replays.

Inside `sandbox()`, work happens in a workspace created for it and loaded with the sample
portfolio and lessons; trackers read that demo data and nothing is sent to notifiers
(`registry.demo_only`). The workspace's budgets come along: the sandbox may spend only what is
left of the month's budget, and the per-run budget applies as it is.

On the way out, the LLM spend is kept: each call is copied into the original workspace's cost
ledger (no run, `purpose` set), because the money was really spent. Everything else, and the
workspace itself, is erased.
"""
from __future__ import annotations

import json
import uuid
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import delete, select

from ma_pmo.core import budgets, workspace
from ma_pmo.db import workspaces
from ma_pmo.db.init import FIXTURE, load_fixtures, load_lessons
from ma_pmo.db.models import Base, LlmCall, Scoped, Workspace
from ma_pmo.db.session import get_session
from ma_pmo.integrations.registry import demo_only

PREFIX = "sandbox-"


def demo_scope() -> str:
    """The sample portfolio every sandbox holds."""
    return str(json.loads(FIXTURE.read_text(encoding="utf-8"))["portfolio"]["id"])


@contextmanager
def sandbox(purpose: str) -> Iterator[str]:
    origin = workspace.current()
    allowance = _allowance()
    name = f"{PREFIX}{uuid.uuid4().hex[:12]}"
    workspaces.create(name, purpose)
    try:
        with workspace.use(name), demo_only():
            load_fixtures()
            load_lessons()
            for kind, limit in allowance.items():
                budgets.set_budget(kind, None, limit, purpose)
            yield name
    finally:
        _keep_spend(name, origin, purpose)
        erase(name)


def _allowance() -> dict[str, float]:
    """The hard limits of this workspace, the month's reduced to what is left of it."""
    now = budgets.status()
    out: dict[str, float] = {}
    if now["month"]["limit_usd"] is not None:
        out["month"] = max(0.0, now["month"]["limit_usd"] - now["month"]["spent_usd"])
    if now["run"]["limit_usd"] is not None:
        out["run"] = now["run"]["limit_usd"]
    return out


def _keep_spend(name: str, origin: str, purpose: str) -> None:
    with workspace.use(name), get_session() as s:
        calls = [(c.agent, c.model, c.prompt_tokens, c.completion_tokens, c.cache_read_tokens,
                  c.cache_write_tokens, c.usd, c.price_version, c.latency_ms, c.created_at)
                 for c in s.scalars(select(LlmCall))]
    if not calls:
        return
    with workspace.use(origin), get_session() as s:
        for (agent, model, prompt, completion, read, written, usd, version, latency,
             at) in calls:
            s.add(LlmCall(agent=agent, model=model, prompt_tokens=prompt,
                          completion_tokens=completion, cache_read_tokens=read,
                          cache_write_tokens=written, usd=usd, price_version=version,
                          latency_ms=latency, created_at=at, purpose=purpose))


def erase(name: str) -> None:
    """Delete every row of a workspace, then the workspace."""
    scoped = {m.persist_selectable: m.class_ for m in Base.registry.mappers
              if issubclass(m.class_, Scoped)}
    with workspace.use(name), get_session() as s:
        for table in reversed(Base.metadata.sorted_tables):  # children before parents
            if table in scoped:
                s.execute(delete(scoped[table]))
    with get_session() as s:
        s.execute(delete(Workspace).where(Workspace.id == name))
