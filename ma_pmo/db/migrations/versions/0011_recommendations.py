"""Replay recommendations, and the purpose of spend made outside real runs.

Revision ID: 0011_recommendations
Revises: 0010_budgets
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0011_recommendations"
down_revision = "0010_budgets"
branch_labels = None
depends_on = None

RULE = ("current_setting('ma_pmo.all_workspaces', true) = 'on' "
        "OR workspace_id = current_setting('ma_pmo.workspace', true)")


def upgrade() -> None:
    with op.batch_alter_table("llm_call") as batch:
        batch.add_column(sa.Column("purpose", sa.String(), nullable=True))
    op.create_table(
        "recommendation",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("workflow_id", sa.String(), nullable=False),
        sa.Column("step_id", sa.String(), nullable=False),
        sa.Column("base_version", sa.Integer(), nullable=False),
        sa.Column("verdict", sa.String(), nullable=False),
        sa.Column("report", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("created_by", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("decided_by", sa.String(), nullable=True),
        sa.Column("decided_at", sa.DateTime(), nullable=True),
        sa.Column("draft_version", sa.Integer(), nullable=True),
        sa.Column("workspace_id", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspace.id"],
                                name="recommendation_workspace_id_fkey"),
        sa.PrimaryKeyConstraint("id", name="recommendation_pkey"),
    )
    op.create_index("ix_recommendation_workflow_id", "recommendation", ["workflow_id"])
    op.create_index("ix_recommendation_workspace_id", "recommendation", ["workspace_id"])
    if op.get_bind().dialect.name == "postgresql":  # same isolation as 0007
        op.execute("ALTER TABLE recommendation ENABLE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE recommendation FORCE ROW LEVEL SECURITY")
        op.execute(f"CREATE POLICY workspace_isolation ON recommendation USING ({RULE}) "
                   f"WITH CHECK ({RULE})")


def downgrade() -> None:
    op.drop_index("ix_recommendation_workspace_id", table_name="recommendation")
    op.drop_index("ix_recommendation_workflow_id", table_name="recommendation")
    op.drop_table("recommendation")
    with op.batch_alter_table("llm_call") as batch:
        batch.drop_column("purpose")
