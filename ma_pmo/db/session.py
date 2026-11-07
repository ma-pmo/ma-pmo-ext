"""Engine and session factory. SQLite by default; switch to Postgres via DB_URL."""
from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine, event
from sqlalchemy.orm import ORMExecuteState, Session, sessionmaker, with_loader_criteria

from ma_pmo.core import workspace
from ma_pmo.core.config import get_settings
from ma_pmo.db.models import Scoped

_settings = get_settings()

# SQLite must allow cross-thread use (FastAPI/LangGraph are multi-threaded)
_connect_args = (
    {"check_same_thread": False} if _settings.db_url.startswith("sqlite") else {}
)
engine = create_engine(_settings.db_url, connect_args=_connect_args, future=True)


if engine.dialect.name == "postgresql":
    @event.listens_for(engine, "connect")
    def _session_in_utc(dbapi_connection, _record) -> None:  # type: ignore[no-untyped-def]
        """Columns are timezone-less and the app writes UTC, so a session in Asia/Seoul would
        shift every timestamp by nine hours. Set here because PGTZ overrides connect options."""
        with dbapi_connection.cursor() as cursor:
            cursor.execute("SET TIME ZONE 'UTC'")
        dbapi_connection.commit()


SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, class_=Session)


@event.listens_for(Session, "do_orm_execute")
def _only_current_workspace(state: ORMExecuteState) -> None:
    """Every ORM SELECT, UPDATE and DELETE sees only the current workspace's rows, including
    joins and subqueries. Core statements on a raw connection are not filtered."""
    if state.is_column_load or state.is_relationship_load:  # their parent query was filtered
        return
    if not (state.is_select or state.is_update or state.is_delete):
        return
    if state.execution_options.get(workspace.ALL_WORKSPACES):
        return
    current = workspace.current()
    state.statement = state.statement.options(with_loader_criteria(
        Scoped, lambda cls: cls.workspace_id == current, include_aliases=True))


def ensure_schema() -> None:
    """Create or upgrade the schema through migrations, the only path that changes it."""
    from ma_pmo.db.migrate import upgrade

    upgrade(engine)


@contextmanager
def get_session() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
