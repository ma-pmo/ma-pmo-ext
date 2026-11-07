"""Which workspace the current code works in.

A request sets it from the `X-Workspace` header; the CLI, the MCP server and background work
use `MA_PMO_WORKSPACE` (default `default`). Every ORM query is filtered by it and every new row
is created in it (`ma_pmo/db/session.py`, `ma_pmo/db/models.py`), so code does not filter by
hand. Work that must see every workspace says so with `ALL_WORKSPACES`.
"""
from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

from ma_pmo.core.config import get_settings

DEFAULT_WORKSPACE = "default"
ALL_WORKSPACES = "all_workspaces"  # execution option: skip the filter for one statement
HEADER = "X-Workspace"

_current: ContextVar[str | None] = ContextVar("ma_pmo_workspace", default=None)


def current() -> str:
    return _current.get() or get_settings().workspace


@contextmanager
def use(workspace_id: str) -> Iterator[str]:
    token = _current.set(workspace_id)
    try:
        yield workspace_id
    finally:
        _current.reset(token)
