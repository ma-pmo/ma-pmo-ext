"""Versioned policy and the guardrail log (roadmap 10, step 1).

Revision ID: 0020_policy_guardrails
Revises: 0019_role_assignments
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0020_policy_guardrails"
down_revision = "0019_role_assignments"
branch_labels = None
depends_on = None

RULE = ("current_setting('ma_pmo.all_workspaces', true) = 'on' "
        "OR workspace_id = current_setting('ma_pmo.workspace', true)")
CHECK_INDEXED = ("name", "point", "decision", "run_id", "workspace_id")


def _isolate(table: str) -> None:
    if op.get_bind().dialect.name == "postgresql":  # same isolation as 0007
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(f"CREATE POLICY workspace_isolation ON {table} USING ({RULE}) "
                   f"WITH CHECK ({RULE})")


def upgrade() -> None:
    op.create_table(
        "policy",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("document", sa.JSON(), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("created_by", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("workspace_id", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspace.id"],
                                name="policy_workspace_id_fkey"),
        sa.PrimaryKeyConstraint("id", name="policy_pkey"),
        sa.UniqueConstraint("workspace_id", "version", name="uq_policy_version"),
    )
    op.create_index("ix_policy_workspace_id", "policy", ["workspace_id"])
    _isolate("policy")
    op.create_table(
        "guardrail_check",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("point", sa.String(), nullable=False),
        sa.Column("mode", sa.String(), nullable=False),
        sa.Column("decision", sa.String(), nullable=False),
        sa.Column("outcome", sa.String(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("detail", sa.JSON(), nullable=True),
        sa.Column("policy_version", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.String(), nullable=True),
        sa.Column("message_id", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("workspace_id", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspace.id"],
                                name="guardrail_check_workspace_id_fkey"),
        sa.PrimaryKeyConstraint("id", name="guardrail_check_pkey"),
    )
    for column in CHECK_INDEXED:
        op.create_index(f"ix_guardrail_check_{column}", "guardrail_check", [column])
    _isolate("guardrail_check")


def downgrade() -> None:
    for column in CHECK_INDEXED:
        op.drop_index(f"ix_guardrail_check_{column}", table_name="guardrail_check")
    op.drop_table("guardrail_check")
    op.drop_index("ix_policy_workspace_id", table_name="policy")
    op.drop_table("policy")
