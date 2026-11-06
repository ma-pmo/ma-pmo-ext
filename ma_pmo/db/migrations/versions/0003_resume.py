"""Resumable runs: saved state and results, leases, and retry-safe rows.

Revision ID: 0003_resume
Revises: 0002_runs
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003_resume"
down_revision = "0002_runs"
branch_labels = None
depends_on = None

_KEYED = ("agent_message", "kpi_event")


def upgrade() -> None:
    with op.batch_alter_table("run") as batch:
        batch.add_column(sa.Column("state", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("result", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("lease_owner", sa.String(), nullable=True))
        batch.add_column(sa.Column("lease_until", sa.DateTime(), nullable=True))
    with op.batch_alter_table("run_step") as batch:
        batch.add_column(sa.Column("result", sa.JSON(), nullable=True))
    for table in _KEYED:
        with op.batch_alter_table(table) as batch:
            batch.add_column(sa.Column("dedupe_key", sa.String(), nullable=True))
            batch.create_index(f"ix_{table}_dedupe_key", ["dedupe_key"], unique=True)


def downgrade() -> None:
    for table in _KEYED:
        with op.batch_alter_table(table) as batch:
            batch.drop_index(f"ix_{table}_dedupe_key")
            batch.drop_column("dedupe_key")
    with op.batch_alter_table("run_step") as batch:
        batch.drop_column("result")
    with op.batch_alter_table("run") as batch:
        batch.drop_column("lease_until")
        batch.drop_column("lease_owner")
        batch.drop_column("result")
        batch.drop_column("state")
