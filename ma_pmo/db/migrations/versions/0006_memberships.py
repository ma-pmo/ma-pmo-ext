"""Memberships: the roles a principal has in one workspace.

Revision ID: 0006_memberships
Revises: 0005_workspaces
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0006_memberships"
down_revision = "0005_workspaces"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "membership",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("workspace_id", sa.String(), nullable=False),
        sa.Column("principal", sa.String(), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspace.id"],
                                name="membership_workspace_id_fkey"),
        sa.PrimaryKeyConstraint("id", name="membership_pkey"),
        sa.UniqueConstraint("workspace_id", "principal", "role", name="uq_membership"),
    )
    op.create_index("ix_membership_principal", "membership", ["principal"])


def downgrade() -> None:
    op.drop_index("ix_membership_principal", table_name="membership")
    op.drop_table("membership")
