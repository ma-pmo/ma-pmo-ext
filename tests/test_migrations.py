"""Schema migrations: new databases, adopting 0.4 databases, and drift from the models."""
from __future__ import annotations

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect, text

from ma_pmo.db import migrate
from ma_pmo.db.models import Base


def _engine(tmp_path, name="m.db"):
    return create_engine(f"sqlite:///{tmp_path / name}")


@pytest.mark.smoke
def test_new_database_reaches_head_and_upgrade_is_repeatable(tmp_path):
    engine = _engine(tmp_path)
    assert migrate.current(engine) is None
    assert migrate.upgrade(engine) == migrate.head()
    assert migrate.upgrade(engine) == migrate.head()
    assert set(Base.metadata.tables) <= set(inspect(engine).get_table_names())


def test_models_match_migrations(tmp_path):
    """Fails when a model changes without a migration."""
    engine = _engine(tmp_path)
    migrate.upgrade(engine)
    with engine.connect() as conn:
        ctx = MigrationContext.configure(conn, opts={"compare_type": True})
        assert compare_metadata(ctx, Base.metadata) == []


def test_database_from_before_migrations_is_adopted_with_its_data(tmp_path):
    engine = _engine(tmp_path)
    migrate.upgrade(engine, migrate.BASELINE)  # the 0.4 tables...
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE alembic_version"))  # ...which had no version record
        conn.execute(text("INSERT INTO portfolio (id, name, period) VALUES ('P', 'Kept', 'Q1')"))
    assert migrate.current(engine) is None

    assert migrate.upgrade(engine) == migrate.head()
    with engine.connect() as conn:
        assert conn.execute(text("SELECT name FROM portfolio")).scalar_one() == "Kept"


def test_status_command_at_head(capsys):
    from ma_pmo.cli import _cmd_db

    assert _cmd_db("status") == 0  # the shared test database is already at head
    assert migrate.head() in capsys.readouterr().out
