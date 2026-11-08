"""Why an approval was asked for: the commit gate's challenges and missing reviews.

Revision ID: 0013_approval_reason
Revises: 0012_message_evidence
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0013_approval_reason"
down_revision = "0012_message_evidence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("approval") as batch:
        batch.add_column(sa.Column("reason", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("approval") as batch:
        batch.drop_column("reason")
