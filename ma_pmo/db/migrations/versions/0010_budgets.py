"""Budgets: a monthly and a per-run spending limit per workspace.

Revision ID: 0010_budgets
Revises: 0009_llm_calls
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0010_budgets"
down_revision = "0009_llm_calls"
branch_labels = None
depends_on = None

RULE = ("current_setting('ma_pmo.all_workspaces', true) = 'on' "
        "OR workspace_id = current_setting('ma_pmo.workspace', true)")


def upgrade() -> None:
    op.create_table(
        "budget",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("warn_usd", sa.Float(), nullable=True),
        sa.Column("limit_usd", sa.Float(), nullable=True),
        sa.Column("warned_for", sa.String(), nullable=True),
        sa.Column("updated_by", sa.String(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("workspace_id", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspace.id"],
                                name="budget_workspace_id_fkey"),
        sa.PrimaryKeyConstraint("id", name="budget_pkey"),
        sa.UniqueConstraint("workspace_id", "kind", name="uq_budget"),
    )
    op.create_index("ix_budget_workspace_id", "budget", ["workspace_id"])
    if op.get_bind().dialect.name == "postgresql":  # same isolation as 0007
        op.execute("ALTER TABLE budget ENABLE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE budget FORCE ROW LEVEL SECURITY")
        op.execute(f"CREATE POLICY workspace_isolation ON budget USING ({RULE}) "
                   f"WITH CHECK ({RULE})")


def downgrade() -> None:
    op.drop_index("ix_budget_workspace_id", table_name="budget")
    op.drop_table("budget")
