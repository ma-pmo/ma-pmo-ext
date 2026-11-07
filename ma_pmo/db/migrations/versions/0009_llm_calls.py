"""The cost ledger: one row per LLM call, with tokens and USD.

Revision ID: 0009_llm_calls
Revises: 0008_workflow_versions
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0009_llm_calls"
down_revision = "0008_workflow_versions"
branch_labels = None
depends_on = None

RULE = ("current_setting('ma_pmo.all_workspaces', true) = 'on' "
        "OR workspace_id = current_setting('ma_pmo.workspace', true)")


def upgrade() -> None:
    op.create_table(
        "llm_call",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.String(), nullable=True),
        sa.Column("step_seq", sa.Integer(), nullable=True),
        sa.Column("agent", sa.String(), nullable=False),
        sa.Column("model", sa.String(), nullable=False),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False),
        sa.Column("completion_tokens", sa.Integer(), nullable=False),
        sa.Column("cache_read_tokens", sa.Integer(), nullable=False),
        sa.Column("cache_write_tokens", sa.Integer(), nullable=False),
        sa.Column("usd", sa.Float(), nullable=True),
        sa.Column("price_version", sa.String(), nullable=True),
        sa.Column("latency_ms", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("workspace_id", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspace.id"],
                                name="llm_call_workspace_id_fkey"),
        sa.PrimaryKeyConstraint("id", name="llm_call_pkey"),
    )
    for column in ("run_id", "model", "created_at", "workspace_id"):
        op.create_index(f"ix_llm_call_{column}", "llm_call", [column])
    if op.get_bind().dialect.name == "postgresql":  # same isolation as 0007
        op.execute("ALTER TABLE llm_call ENABLE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE llm_call FORCE ROW LEVEL SECURITY")
        op.execute(f"CREATE POLICY workspace_isolation ON llm_call USING ({RULE}) "
                   f"WITH CHECK ({RULE})")


def downgrade() -> None:
    for column in ("run_id", "model", "created_at", "workspace_id"):
        op.drop_index(f"ix_llm_call_{column}", table_name="llm_call")
    op.drop_table("llm_call")
