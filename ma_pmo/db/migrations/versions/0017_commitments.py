"""Commitments: who owes what to whom, by when (Singh; roadmap 9).

Revision ID: 0017_commitments
Revises: 0016_communications
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0017_commitments"
down_revision = "0016_communications"
branch_labels = None
depends_on = None

RULE = ("current_setting('ma_pmo.all_workspaces', true) = 'on' "
        "OR workspace_id = current_setting('ma_pmo.workspace', true)")
INDEXED = ("state", "debtor", "project_id", "source_message", "workspace_id")


def upgrade() -> None:
    op.create_table(
        "commitment",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("debtor", sa.String(), nullable=False),
        sa.Column("creditor", sa.String(), nullable=False),
        sa.Column("antecedent", sa.Text(), nullable=True),
        sa.Column("consequent", sa.Text(), nullable=False),
        sa.Column("detach_by", sa.DateTime(), nullable=True),
        sa.Column("due", sa.DateTime(), nullable=True),
        sa.Column("state", sa.String(), nullable=False),
        sa.Column("project_id", sa.String(), nullable=True),
        sa.Column("source_message", sa.String(), nullable=True),
        sa.Column("source_decision", sa.String(), nullable=True),
        sa.Column("source_approval", sa.Integer(), nullable=True),
        sa.Column("conversation_id", sa.String(), nullable=True),
        sa.Column("check", sa.JSON(), nullable=True),
        sa.Column("evidence", sa.JSON(), nullable=True),
        sa.Column("history", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("workspace_id", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspace.id"],
                                name="commitment_workspace_id_fkey"),
        sa.PrimaryKeyConstraint("id", name="commitment_pkey"),
    )
    for column in INDEXED:
        op.create_index(f"ix_commitment_{column}", "commitment", [column])
    if op.get_bind().dialect.name == "postgresql":  # same isolation as 0007
        op.execute("ALTER TABLE commitment ENABLE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE commitment FORCE ROW LEVEL SECURITY")
        op.execute(f"CREATE POLICY workspace_isolation ON commitment USING ({RULE}) "
                   f"WITH CHECK ({RULE})")


def downgrade() -> None:
    for column in INDEXED:
        op.drop_index(f"ix_commitment_{column}", table_name="commitment")
    op.drop_table("commitment")
