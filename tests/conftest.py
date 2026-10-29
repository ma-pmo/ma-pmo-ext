"""Test isolation — temporary SQLite DB + fixture load.

The db module must be imported only after DB_URL/CHECKPOINT point to temporary paths, so
environment variables are set at the very top of this file (before any import).
"""
from __future__ import annotations

import os
import tempfile

_tmp = tempfile.mkdtemp(prefix="mapmo-test-")
os.environ["DB_URL"] = f"sqlite:///{_tmp}/test.db"
os.environ["CHECKPOINT_DB"] = f"{_tmp}/ckpt.sqlite"
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")

import pytest  # noqa: E402

from ma_pmo.db.init import load_fixtures, load_lessons  # noqa: E402
from ma_pmo.db.session import create_all  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _db():
    create_all()
    load_fixtures()
    load_lessons()
    yield
