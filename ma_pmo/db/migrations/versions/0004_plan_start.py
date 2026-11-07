"""Portfolios say which ISO week allocation starts from.

Revision ID: 0004_plan_start
Revises: 0003_resume
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0004_plan_start"
down_revision = "0003_resume"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("portfolio") as batch:
        batch.add_column(sa.Column("plan_start", sa.String(), nullable=True))
    # the sample portfolio keeps the week it was written for; others start from the current week
    op.execute("UPDATE portfolio SET plan_start = '2026-W03' WHERE id = 'PORTFOLIO#2026-Q1'")


def downgrade() -> None:
    with op.batch_alter_table("portfolio") as batch:
        batch.drop_column("plan_start")
