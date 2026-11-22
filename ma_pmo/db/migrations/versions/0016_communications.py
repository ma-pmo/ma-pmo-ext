"""Communication log: every notification attempt, sent, failed or skipped (ISO 21502 7.13).

Revision ID: 0016_communications
Revises: 0015_decision_records
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0016_communications"
down_revision = "0015_decision_records"
branch_labels = None
depends_on = None

RULE = ("current_setting('ma_pmo.all_workspaces', true) = 'on' "
        "OR workspace_id = current_setting('ma_pmo.workspace', true)")
INDEXED = ("event", "status", "message_id", "decision_id", "run_id", "workspace_id")


def upgrade() -> None:
    op.create_table(
        "communication",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("event", sa.String(), nullable=False),
        sa.Column("channel", sa.String(), nullable=False),
        sa.Column("target", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("severity", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("error", sa.String(), nullable=True),
        sa.Column("message_id", sa.String(), nullable=True),
        sa.Column("decision_id", sa.String(), nullable=True),
        sa.Column("approval_id", sa.Integer(), nullable=True),
        sa.Column("run_id", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("workspace_id", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspace.id"],
                                name="communication_workspace_id_fkey"),
        sa.PrimaryKeyConstraint("id", name="communication_pkey"),
    )
    for column in INDEXED:
        op.create_index(f"ix_communication_{column}", "communication", [column])
    if op.get_bind().dialect.name == "postgresql":  # same isolation as 0007
        op.execute("ALTER TABLE communication ENABLE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE communication FORCE ROW LEVEL SECURITY")
        op.execute(f"CREATE POLICY workspace_isolation ON communication USING ({RULE}) "
                   f"WITH CHECK ({RULE})")


def downgrade() -> None:
    for column in INDEXED:
        op.drop_index(f"ix_communication_{column}", table_name="communication")
    op.drop_table("communication")
