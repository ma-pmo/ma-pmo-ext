"""Test isolation — temporary SQLite DB + fixture load.

The db module must be imported only after DB_URL/CHECKPOINT point to temporary paths, so
environment variables are set at the very top of this file (before any import).
"""
from __future__ import annotations

import os
import tempfile

_tmp = tempfile.mkdtemp(prefix="mapmo-test-")
# TEST_DB_URL runs the suite on another database (CI uses it for Postgres)
os.environ["DB_URL"] = os.environ.get("TEST_DB_URL") or f"sqlite:///{_tmp}/test.db"
os.environ["CHECKPOINT_DB"] = f"{_tmp}/ckpt.sqlite"
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")

import pytest  # noqa: E402

from ma_pmo.db.init import load_fixtures, load_lessons  # noqa: E402
from ma_pmo.db.session import ensure_schema  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _db():
    ensure_schema()
    load_fixtures()
    load_lessons()
    yield


@pytest.fixture(autouse=True)
def _fresh_breakers():
    """A notifier that failed in one test must not be skipped in the next."""
    from ma_pmo.integrations import dispatch

    dispatch.reset_breakers()
    yield
