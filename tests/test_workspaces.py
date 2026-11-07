"""Workspace schema: every table is scoped, ids repeat across workspaces, 0.5 data moves in."""
from __future__ import annotations

import pytest
from alembic import command
from sqlalchemy import create_engine, delete, inspect, select, text

from ma_pmo.core import workspace
from ma_pmo.db import migrate
from ma_pmo.db.models import (
    DEFAULT_WORKSPACE,
    Base,
    Portfolio,
    Project,
    Resource,
    Task,
    Workspace,
)
from ma_pmo.db.session import get_session

# a new table must be scoped or listed here on purpose; memberships are read before the
# request knows its workspace
UNSCOPED = {"workspace", "membership"}


def test_every_table_belongs_to_a_workspace():
    missing = [name for name, table in Base.metadata.tables.items()
               if name not in UNSCOPED and "workspace_id" not in table.c]
    assert missing == []


def test_new_rows_land_in_the_default_workspace():
    assert Project(id="X", portfolio_id="P").workspace_id == DEFAULT_WORKSPACE
    assert Project(id="X", portfolio_id="P", workspace_id="b").workspace_id == "b"


@pytest.fixture
def second_workspace():
    with get_session() as s:
        s.merge(Workspace(id="b", name="B"))
    yield "b"
    with workspace.use("b"), get_session() as s:
        for model in (Task, Project, Resource, Portfolio):
            s.execute(delete(model))
    with get_session() as s:
        s.execute(delete(Workspace).where(Workspace.id == "b"))


def test_the_same_ids_can_live_in_two_workspaces(second_workspace):
    with get_session() as s:
        s.add(Portfolio(id="PORTFOLIO#2026-Q1", name="B's", period="Q1", workspace_id="b"))
        s.flush()
        s.add(Project(id="PROJ-14", portfolio_id="PORTFOLIO#2026-Q1", workspace_id="b"))
        s.add(Resource(id="R-01", skill="x", workspace_id="b"))
    with get_session() as s:
        names = s.execute(select(Portfolio.workspace_id, Portfolio.name)
                          .where(Portfolio.id == "PORTFOLIO#2026-Q1")
                          .order_by(Portfolio.workspace_id),
                          execution_options={workspace.ALL_WORKSPACES: True}).all()
    assert [w for w, _ in names] == ["b", DEFAULT_WORKSPACE]
    assert dict(names)["b"] == "B's"


def _engine(tmp_path):
    return create_engine(f"sqlite:///{tmp_path / 'w.db'}")


def test_a_0_5_database_moves_into_default_with_its_data(tmp_path):
    engine = _engine(tmp_path)
    migrate.upgrade(engine, "0004_plan_start")
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO portfolio (id, name, period) VALUES ('P', 'Kept', 'Q1')"))
        conn.execute(text("INSERT INTO project (id, portfolio_id, skill, status) "
                          "VALUES ('J', 'P', 'x', 'green')"))
        conn.execute(text("INSERT INTO resource (id, skill, capacity) VALUES ('R', 'x', 40)"))
        conn.execute(text("INSERT INTO allocation (project_id, resource_id, week, hours) "
                          "VALUES ('J', 'R', '2026-W03', 8)"))
    assert migrate.upgrade(engine) == migrate.head()
    with engine.connect() as conn:
        assert conn.execute(text("SELECT workspace_id, name FROM portfolio")).one() == (
            DEFAULT_WORKSPACE, "Kept")
        assert conn.execute(text("SELECT workspace_id, project_id, hours FROM allocation")
                            ).one() == (DEFAULT_WORKSPACE, "J", 8.0)
        assert conn.execute(text("SELECT id FROM workspace")).scalars().all() == [
            DEFAULT_WORKSPACE]
    keys = inspect(engine).get_pk_constraint("task")["constrained_columns"]
    assert keys == ["workspace_id", "id"]


def test_downgrade_refuses_when_another_workspace_has_data(tmp_path):
    engine = _engine(tmp_path)
    migrate.upgrade(engine)
    config = migrate._config()
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO workspace (id, name, created_at) "
                          "VALUES ('b', 'B', '2026-01-01')"))
        conn.execute(text("INSERT INTO resource (workspace_id, id, skill, capacity) "
                          "VALUES ('b', 'R', 'x', 40)"))
    with engine.begin() as conn, pytest.raises(RuntimeError, match="outside the default"):
        config.attributes["connection"] = conn
        command.downgrade(config, "0004_plan_start")
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM resource WHERE workspace_id = 'b'"))
    with engine.begin() as conn:
        config.attributes["connection"] = conn
        command.downgrade(config, "0004_plan_start")
    assert migrate.current(engine) == "0004_plan_start"
