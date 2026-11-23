"""When a commitment was violated and how far its escalation chain has gone (roadmap 9, step 2).

Revision ID: 0018_commitment_escalation
Revises: 0017_commitments
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0018_commitment_escalation"
down_revision = "0017_commitments"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("commitment") as batch:
        batch.add_column(sa.Column("violated_at", sa.DateTime(), nullable=True))
        batch.add_column(sa.Column("escalation", sa.Integer(), nullable=False,
                                   server_default="0"))


def downgrade() -> None:
    with op.batch_alter_table("commitment") as batch:
        batch.drop_column("escalation")
        batch.drop_column("violated_at")
