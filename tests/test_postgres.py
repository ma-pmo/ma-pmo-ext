"""Postgres-only behaviour. Runs when TEST_DB_URL points at Postgres (a CI job does)."""
from __future__ import annotations

import os
import threading
import uuid

import pytest
from sqlalchemy import create_engine, text

from ma_pmo.core.state.checkpointer import _psycopg_url, build_checkpointer
from ma_pmo.db import migrate

URL = os.environ.get("TEST_DB_URL", "")
needs_postgres = pytest.mark.skipif(not URL.startswith("postgresql"),
                                    reason="set TEST_DB_URL to a Postgres database")


def test_url_conversion():
    assert _psycopg_url("postgresql+psycopg://u:p@h:5432/d") == "postgresql://u:p@h:5432/d"


@needs_postgres
def test_checkpoints_go_to_postgres_and_survive_a_new_saver():
    from langgraph.graph import END, StateGraph
    from typing_extensions import TypedDict

    class State(TypedDict):
        n: int

    def graph(saver):
        g = StateGraph(State)
        g.add_node("add", lambda s: {"n": s["n"] + 1})
        g.set_entry_point("add")
        g.add_edge("add", END)
        return g.compile(checkpointer=saver)

    config = {"configurable": {"thread_id": uuid.uuid4().hex}}
    first = build_checkpointer()
    assert type(first).__name__ == "PostgresSaver"
    graph(first).invoke({"n": 1}, config=config)
    second = build_checkpointer()  # what a restarted process or another replica would build
    assert graph(second).get_state(config).values == {"n": 2}


@needs_postgres
def test_timestamps_are_utc_whatever_the_server_timezone():
    from ma_pmo.db.session import engine

    with engine.connect() as conn:
        assert conn.execute(text("SHOW timezone")).scalar().upper() in {"UTC", "ETC/UTC"}


@needs_postgres
def test_concurrent_upgrades_take_turns():
    admin = create_engine(URL, isolation_level="AUTOCOMMIT")
    name = f"mig_{uuid.uuid4().hex[:8]}"
    with admin.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{name}"'))
    url = admin.url.set(database=name)
    results: list[str | None] = []

    def upgrade() -> None:
        engine = create_engine(url)
        results.append(migrate.upgrade(engine))
        engine.dispose()

    threads = [threading.Thread(target=upgrade) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert results == [migrate.head()] * 4
    with admin.connect() as conn:
        conn.execute(text(f'DROP DATABASE "{name}" WITH (FORCE)'))


@needs_postgres
def test_a_row_cannot_point_into_another_workspace():
    from sqlalchemy.exc import IntegrityError

    engine = create_engine(URL)
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO workspace (id, name, created_at) "
                          "VALUES ('fk-test', 'T', now())"))
    try:
        with pytest.raises(IntegrityError), engine.begin() as conn:
            # PORTFOLIO#2026-Q1 exists, but only in `default`
            conn.execute(text("INSERT INTO project (workspace_id, id, portfolio_id, skill, status) "
                              "VALUES ('fk-test', 'X', 'PORTFOLIO#2026-Q1', 'x', 'green')"))
    finally:
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM workspace WHERE id = 'fk-test'"))
