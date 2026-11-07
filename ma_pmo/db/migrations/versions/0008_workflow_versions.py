"""Workflow versions: drafts and published versions of a workflow, per workspace.

Revision ID: 0008_workflow_versions
Revises: 0007_row_level_security
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0008_workflow_versions"
down_revision = "0007_row_level_security"
branch_labels = None
depends_on = None

RULE = ("current_setting('ma_pmo.all_workspaces', true) = 'on' "
        "OR workspace_id = current_setting('ma_pmo.workspace', true)")


def upgrade() -> None:
    op.create_table(
        "workflow_version",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("workflow_id", sa.String(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("spec", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("created_by", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("published_by", sa.String(), nullable=True),
        sa.Column("published_at", sa.DateTime(), nullable=True),
        sa.Column("workspace_id", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspace.id"],
                                name="workflow_version_workspace_id_fkey"),
        sa.PrimaryKeyConstraint("id", name="workflow_version_pkey"),
        sa.UniqueConstraint("workspace_id", "workflow_id", "version", name="uq_workflow_version"),
    )
    op.create_index("ix_workflow_version_workflow_id", "workflow_version", ["workflow_id"])
    op.create_index("ix_workflow_version_workspace_id", "workflow_version", ["workspace_id"])
    if op.get_bind().dialect.name == "postgresql":  # same isolation as 0007
        op.execute("ALTER TABLE workflow_version ENABLE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE workflow_version FORCE ROW LEVEL SECURITY")
        op.execute(f"CREATE POLICY workspace_isolation ON workflow_version USING ({RULE}) "
                   f"WITH CHECK ({RULE})")


def downgrade() -> None:
    op.drop_index("ix_workflow_version_workspace_id", table_name="workflow_version")
    op.drop_index("ix_workflow_version_workflow_id", table_name="workflow_version")
    op.drop_table("workflow_version")
