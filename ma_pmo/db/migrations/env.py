"""Alembic environment. Run through `ma_pmo.db.migrate`, which passes the connection in."""
from __future__ import annotations

from alembic import context

from ma_pmo.db.models import Base

connection = context.config.attributes["connection"]
context.configure(
    connection=connection,
    target_metadata=Base.metadata,
    render_as_batch=True,  # SQLite cannot ALTER most things; batch mode rebuilds the table
    compare_type=True,
)
with context.begin_transaction():
    context.run_migrations()
