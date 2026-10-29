"""Engine and session factory. SQLite by default; switch to Postgres via DB_URL."""
from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from ma_pmo.core.config import get_settings
from ma_pmo.db.models import Base

_settings = get_settings()

# SQLite must allow cross-thread use (FastAPI/LangGraph are multi-threaded)
_connect_args = (
    {"check_same_thread": False} if _settings.db_url.startswith("sqlite") else {}
)
engine = create_engine(_settings.db_url, connect_args=_connect_args, future=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, class_=Session)


def create_all() -> None:
    Base.metadata.create_all(engine)


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
