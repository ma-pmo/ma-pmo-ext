"""Postgres-only behaviour. Runs when TEST_DB_URL points at Postgres (a CI job does)."""
from __future__ import annotations

import os
import threading
import uuid
from contextlib import contextmanager

import pytest
from sqlalchemy import create_engine, text

from ma_pmo.core.state.checkpointer import _psycopg_url, build_checkpointer
from ma_pmo.db import migrate
from ma_pmo.db.session import see_every_workspace

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
            see_every_workspace(conn)  # past row-level security, so the foreign key decides
            # PORTFOLIO#2026-Q1 exists, but only in `default`
            conn.execute(text("INSERT INTO project (workspace_id, id, portfolio_id, skill, status) "
                              "VALUES ('fk-test', 'X', 'PORTFOLIO#2026-Q1', 'x', 'green')"))
    finally:
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM workspace WHERE id = 'fk-test'"))


TENANT_TABLES = ("portfolio", "project", "task", "resource", "allocation", "risk", "report", "run",
                 "run_step", "agent_message", "approval", "knowledge_doc", "kpi_event",
                 "workflow_version", "llm_call")


@needs_postgres
def test_every_scoped_table_has_forced_row_level_security():
    from ma_pmo.db.models import Base, Scoped

    scoped = {m.class_.__tablename__ for m in Base.registry.mappers
              if issubclass(m.class_, Scoped)}
    assert scoped == set(TENANT_TABLES)  # a new table needs a policy in a migration
    with create_engine(URL).connect() as conn:
        rows = conn.execute(text(
            "SELECT relname, relrowsecurity, relforcerowsecurity FROM pg_class "
            "WHERE relname = ANY(:names)"), {"names": list(scoped)}).all()
    assert {name for name, on, forced in rows if on and forced} == scoped


@contextmanager
def _subject_to_rls():
    """A transaction that row-level security applies to: superusers bypass it, so they switch
    to a plain role; the CI job already connects as one (the table owner, held by FORCE)."""
    engine = create_engine(URL)
    with engine.begin() as conn:
        if conn.execute(text("SELECT rolsuper FROM pg_roles WHERE rolname = current_user")
                        ).scalar_one():
            role = f"rls_{uuid.uuid4().hex[:8]}"
            conn.execute(text(f"CREATE ROLE {role} NOLOGIN"))
            conn.execute(text(f"GRANT SELECT, INSERT ON ALL TABLES IN SCHEMA public TO {role}"))
            conn.execute(text(f"GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO {role}"))
            conn.execute(text(f"SET LOCAL ROLE {role}"))
        yield conn
        conn.rollback()  # leaves no role or row behind
    engine.dispose()


def _set(conn, name: str, value: str) -> None:
    conn.execute(text(f"SELECT set_config('ma_pmo.{name}', :v, true)"), {"v": value})


@needs_postgres
def test_postgres_itself_hides_other_workspaces():
    with _subject_to_rls() as conn:
        count = "SELECT COUNT(*) FROM project"
        assert conn.execute(text(count)).scalar_one() == 0  # nobody said which workspace
        _set(conn, "workspace", "default")
        mine = conn.execute(text(count)).scalar_one()
        assert mine > 0
        assert conn.execute(text("SELECT COUNT(*) FROM project WHERE workspace_id <> 'default'")
                            ).scalar_one() == 0
        _set(conn, "workspace", "elsewhere")
        assert conn.execute(text(count)).scalar_one() == 0
        _set(conn, "all_workspaces", "on")
        assert conn.execute(text(count)).scalar_one() >= mine


@needs_postgres
def test_postgres_refuses_a_row_for_another_workspace():
    from sqlalchemy.exc import ProgrammingError

    with _subject_to_rls() as conn:
        _set(conn, "workspace", "default")
        conn.execute(text("SAVEPOINT before"))
        with pytest.raises(ProgrammingError, match="row-level security"):
            conn.execute(text("INSERT INTO kpi_event (workspace_id, axis, metric, value, meta, ts)"
                              " VALUES ('elsewhere', 'time', 'x', 1, '{}', now())"))
        conn.execute(text("ROLLBACK TO SAVEPOINT before"))
