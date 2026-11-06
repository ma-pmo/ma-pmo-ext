"""The contract check runs the agent, so it needs a database with the demo portfolio."""
import os
import tempfile

os.environ["DB_URL"] = f"sqlite:///{tempfile.mkdtemp(prefix='budget-agent-')}/test.db"

import pytest  # noqa: E402

from ma_pmo.db.init import load_fixtures  # noqa: E402
from ma_pmo.db.session import ensure_schema  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _db():
    ensure_schema()
    load_fixtures()
