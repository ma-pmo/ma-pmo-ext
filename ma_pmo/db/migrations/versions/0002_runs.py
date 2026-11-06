"""Run records: run, run_step, and run_id on messages, approvals and KPI events.

Revision ID: 0002_runs
Revises: 0001_baseline
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002_runs"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None

_LINKED = ("agent_message", "approval", "kpi_event")


def upgrade() -> None:
    op.create_table(
        "run",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("workflow", sa.String(), nullable=False),
        sa.Column("scope", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("thread_id", sa.String(), nullable=True),
        sa.Column("trace_id", sa.String(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_run_status", "run", ["status"])
    op.create_table(
        "run_step",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("agent", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("output_schemas", sa.JSON(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["run_id"], ["run.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "seq", name="uq_run_step_run_id_seq"),
    )
    op.create_index("ix_run_step_run_id", "run_step", ["run_id"])
    for table in _LINKED:
        with op.batch_alter_table(table) as batch:
            batch.add_column(sa.Column("run_id", sa.String(), nullable=True))
            batch.create_foreign_key(f"fk_{table}_run_id", "run", ["run_id"], ["id"])
            batch.create_index(f"ix_{table}_run_id", ["run_id"])


def downgrade() -> None:
    for table in _LINKED:
        with op.batch_alter_table(table) as batch:
            batch.drop_index(f"ix_{table}_run_id")
            batch.drop_constraint(f"fk_{table}_run_id", type_="foreignkey")
            batch.drop_column("run_id")
    op.drop_index("ix_run_step_run_id", table_name="run_step")
    op.drop_table("run_step")
    op.drop_index("ix_run_status", table_name="run")
    op.drop_table("run")
