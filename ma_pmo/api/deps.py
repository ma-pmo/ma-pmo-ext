"""API dependencies — compiled graph singleton."""
from __future__ import annotations

from functools import lru_cache

from ma_pmo.core.graph import build_graph


@lru_cache
def get_graph():
    """Supervisor graph (singleton), reused for the app lifetime."""
    return build_graph()
