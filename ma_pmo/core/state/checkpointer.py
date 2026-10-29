"""LangGraph checkpointer factory — state resume and audit.

Lightweight first: SqliteSaver. Switch to PostgresSaver in production (see below).
"""
from __future__ import annotations

import sqlite3

from langgraph.checkpoint.sqlite import SqliteSaver

from ma_pmo.core.config import get_settings

_settings = get_settings()


def build_checkpointer() -> SqliteSaver:
    """SQLite checkpointer, required to resume HITL interrupts and restore state.

    Production switch:
        from langgraph.checkpoint.postgres import PostgresSaver
        return PostgresSaver.from_conn_string(settings.db_url)
    """
    conn = sqlite3.connect(_settings.checkpoint_db, check_same_thread=False)
    return SqliteSaver(conn)
