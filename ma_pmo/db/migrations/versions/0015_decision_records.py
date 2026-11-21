"""Decision records (MADR fields) and the reason a person gives for an approval.

Revision ID: 0015_decision_records
Revises: 0014_message_envelope
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0015_decision_records"
down_revision = "0014_message_envelope"
branch_labels = None
depends_on = None

RULE = ("current_setting('ma_pmo.all_workspaces', true) = 'on' "
        "OR workspace_id = current_setting('ma_pmo.workspace', true)")


def upgrade() -> None:
    with op.batch_alter_table("approval") as batch:
        batch.add_column(sa.Column("rationale", sa.Text(), nullable=True))
    op.create_table(
        "decision_record",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("subject", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("context", sa.Text(), nullable=True),
        sa.Column("drivers", sa.JSON(), nullable=True),
        sa.Column("options", sa.JSON(), nullable=True),
        sa.Column("outcome", sa.JSON(), nullable=True),
        sa.Column("decision_makers", sa.JSON(), nullable=True),
        sa.Column("consulted", sa.JSON(), nullable=True),
        sa.Column("informed", sa.JSON(), nullable=True),
        sa.Column("consequences", sa.JSON(), nullable=True),
        sa.Column("supersedes", sa.String(), nullable=True),
        sa.Column("run_id", sa.String(), nullable=True),
        sa.Column("message_id", sa.String(), nullable=True),
        sa.Column("approval_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("workspace_id", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspace.id"],
                                name="decision_record_workspace_id_fkey"),
        sa.PrimaryKeyConstraint("id", name="decision_record_pkey"),
    )
    for column in ("kind", "subject", "message_id", "run_id", "workspace_id"):
        op.create_index(f"ix_decision_record_{column}", "decision_record", [column])
    if op.get_bind().dialect.name == "postgresql":  # same isolation as 0007
        op.execute("ALTER TABLE decision_record ENABLE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE decision_record FORCE ROW LEVEL SECURITY")
        op.execute(f"CREATE POLICY workspace_isolation ON decision_record USING ({RULE}) "
                   f"WITH CHECK ({RULE})")


def downgrade() -> None:
    for column in ("kind", "subject", "message_id", "run_id", "workspace_id"):
        op.drop_index(f"ix_decision_record_{column}", table_name="decision_record")
    op.drop_table("decision_record")
    with op.batch_alter_table("approval") as batch:
        batch.drop_column("rationale")
