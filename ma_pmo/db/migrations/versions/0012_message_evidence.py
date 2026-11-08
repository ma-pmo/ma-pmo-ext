"""What a message rests on: evidence references on the message log.

Revision ID: 0012_message_evidence
Revises: 0011_recommendations
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0012_message_evidence"
down_revision = "0011_recommendations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("agent_message") as batch:
        batch.add_column(sa.Column("evidence", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("agent_message") as batch:
        batch.drop_column("evidence")
