"""LangGraph checkpointer factory — state resume and audit.

Follows `DB_URL`: with Postgres, checkpoints live in the same database, so they survive a
restart and every API replica sees them (`pip install "ma-pmo[postgres]"`). Otherwise they go
to the SQLite file `CHECKPOINT_DB`.
"""
from __future__ import annotations

import sqlite3
from typing import Any

from langgraph.checkpoint.sqlite import SqliteSaver

from ma_pmo.core.config import get_settings


def _psycopg_url(db_url: str) -> str:
    """SQLAlchemy's `postgresql+psycopg://` as the plain URL psycopg expects."""
    return "postgresql://" + db_url.split("://", 1)[1]


def _postgres_saver(db_url: str) -> Any:
    try:
        from langgraph.checkpoint.postgres import PostgresSaver
        from psycopg.rows import dict_row
        from psycopg_pool import ConnectionPool
    except ImportError as e:  # optional dependency
        raise ImportError('Postgres needs the extra: pip install "ma-pmo[postgres]"') from e

    pool: Any = ConnectionPool(
        _psycopg_url(db_url), open=True, max_size=10,
        kwargs={"autocommit": True, "row_factory": dict_row, "prepare_threshold": 0},
    )
    saver = PostgresSaver(pool)
    saver.setup()  # creates or upgrades its own tables; safe to repeat
    return saver


def build_checkpointer() -> Any:
    """The checkpointer that resumes HITL interrupts and restores state."""
    settings = get_settings()
    if settings.db_url.startswith("postgresql"):
        return _postgres_saver(settings.db_url)
    conn = sqlite3.connect(settings.checkpoint_db, check_same_thread=False)
    return SqliteSaver(conn)
