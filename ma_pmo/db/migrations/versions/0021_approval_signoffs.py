"""Sign-offs on an approval, for decisions two people must approve (roadmap 10, step 4).

Revision ID: 0021_approval_signoffs
Revises: 0020_policy_guardrails
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0021_approval_signoffs"
down_revision = "0020_policy_guardrails"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("approval") as batch:
        batch.add_column(sa.Column("signoffs", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("approval") as batch:
        batch.drop_column("signoffs")
