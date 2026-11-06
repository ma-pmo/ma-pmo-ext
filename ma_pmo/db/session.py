"""Engine and session factory. SQLite by default; switch to Postgres via DB_URL."""
from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from ma_pmo.core.config import get_settings

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
