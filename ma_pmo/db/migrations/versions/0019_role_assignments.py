"""RACI roles per decision kind and project (roadmap 9, step 4).

Revision ID: 0019_role_assignments
Revises: 0018_commitment_escalation
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0019_role_assignments"
down_revision = "0018_commitment_escalation"
branch_labels = None
depends_on = None

RULE = ("current_setting('ma_pmo.all_workspaces', true) = 'on' "
        "OR workspace_id = current_setting('ma_pmo.workspace', true)")


def upgrade() -> None:
    op.create_table(
        "role_assignment",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("project_id", sa.String(), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("person", sa.String(), nullable=False),
        sa.Column("created_by", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("workspace_id", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspace.id"],
                                name="role_assignment_workspace_id_fkey"),
        sa.PrimaryKeyConstraint("id", name="role_assignment_pkey"),
        sa.UniqueConstraint("workspace_id", "kind", "project_id", "role", "person",
                            name="uq_role_assignment"),
    )
    op.create_index("ix_role_assignment_workspace_id", "role_assignment", ["workspace_id"])
    if op.get_bind().dialect.name == "postgresql":  # same isolation as 0007
        op.execute("ALTER TABLE role_assignment ENABLE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE role_assignment FORCE ROW LEVEL SECURITY")
        op.execute(f"CREATE POLICY workspace_isolation ON role_assignment USING ({RULE}) "
                   f"WITH CHECK ({RULE})")


def downgrade() -> None:
    op.drop_index("ix_role_assignment_workspace_id", table_name="role_assignment")
    op.drop_table("role_assignment")
