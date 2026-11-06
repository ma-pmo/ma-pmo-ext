"""Schema migrations — one path for new databases and upgrades.

    ma-pmo db upgrade      # bring the database to the latest schema
    ma-pmo db status       # current and latest revision

A database created by 0.4 or earlier has the tables but no version record. It is recognized
and stamped at the baseline (which is exactly that schema), then upgraded like any other.
"""
from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Engine, inspect

BASELINE = "0001_baseline"
_MIGRATIONS = Path(__file__).parent / "migrations"


def _config() -> Config:
    config = Config()
    config.set_main_option("script_location", str(_MIGRATIONS))
    return config


def _engine(engine: Engine | None) -> Engine:
    if engine is not None:
        return engine
    from ma_pmo.db.session import engine as default_engine

    return default_engine


def head() -> str | None:
    return ScriptDirectory.from_config(_config()).get_current_head()


def current(engine: Engine | None = None) -> str | None:
    with _engine(engine).connect() as conn:
        return MigrationContext.configure(conn).get_current_revision()


def upgrade(engine: Engine | None = None, revision: str = "head") -> str | None:
    """Migrate to `revision`, adopting a pre-migration database first. Safe to run repeatedly."""
    config = _config()
    with _engine(engine).begin() as conn:
        config.attributes["connection"] = conn
        tables = set(inspect(conn).get_table_names())
        unversioned = "alembic_version" not in tables
        if unversioned and "portfolio" in tables:
            command.stamp(config, BASELINE)
        command.upgrade(config, revision)
    return current(engine)


def downgrade(engine: Engine | None = None, revision: str = BASELINE) -> str | None:
    """Step back to `revision`. Dropped columns lose their data: back up first."""
    config = _config()
    with _engine(engine).begin() as conn:
        config.attributes["connection"] = conn
        command.downgrade(config, revision)
    return current(engine)
