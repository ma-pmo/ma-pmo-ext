"""Conversation envelope on the message log: which conversation, what it answers, reply by when
(FIPA ACL conversation-id, in-reply-to, reply-by).

Revision ID: 0014_message_envelope
Revises: 0013_approval_reason
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0014_message_envelope"
down_revision = "0013_approval_reason"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("agent_message") as batch:
        batch.add_column(sa.Column("conversation_id", sa.String(), nullable=True))
        batch.add_column(sa.Column("in_reply_to", sa.String(), nullable=True))
        batch.add_column(sa.Column("reply_by", sa.DateTime(), nullable=True))
        batch.create_index("ix_agent_message_conversation_id", ["conversation_id"])
        batch.create_index("ix_agent_message_in_reply_to", ["in_reply_to"])


def downgrade() -> None:
    with op.batch_alter_table("agent_message") as batch:
        batch.drop_index("ix_agent_message_in_reply_to")
        batch.drop_index("ix_agent_message_conversation_id")
        batch.drop_column("reply_by")
        batch.drop_column("in_reply_to")
        batch.drop_column("conversation_id")
