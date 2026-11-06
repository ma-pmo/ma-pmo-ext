"""Baseline: the schema as shipped in MA-PMO 0.4.

Revision ID: 0001_baseline
Revises:
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("agent_message",
    sa.Column("message_id", sa.String(), nullable=False),
    sa.Column("sender", sa.String(), nullable=False),
    sa.Column("receiver", sa.String(), nullable=False),
    sa.Column("intent", sa.String(), nullable=False),
    sa.Column("task_ref", sa.String(), nullable=False),
    sa.Column("payload", sa.JSON(), nullable=False),
    sa.Column("confidence", sa.Float(), nullable=False),
    sa.Column("human_gate_required", sa.Boolean(), nullable=False),
    sa.Column("timestamp", sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint("message_id")
    )
    op.create_table("knowledge_doc",
    sa.Column("id", sa.String(), nullable=False),
    sa.Column("project_ref", sa.String(), nullable=False),
    sa.Column("title", sa.String(), nullable=False),
    sa.Column("text", sa.Text(), nullable=False),
    sa.Column("tags", sa.JSON(), nullable=False),
    sa.Column("translations", sa.JSON(), nullable=False),
    sa.PrimaryKeyConstraint("id")
    )
    op.create_table("kpi_event",
    sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
    sa.Column("axis", sa.String(), nullable=False),
    sa.Column("metric", sa.String(), nullable=False),
    sa.Column("value", sa.Float(), nullable=False),
    sa.Column("project_id", sa.String(), nullable=True),
    sa.Column("meta", sa.JSON(), nullable=False),
    sa.Column("ts", sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint("id")
    )
    op.create_table("portfolio",
    sa.Column("id", sa.String(), nullable=False),
    sa.Column("name", sa.String(), nullable=False),
    sa.Column("period", sa.String(), nullable=False),
    sa.PrimaryKeyConstraint("id")
    )
    op.create_table("report",
    sa.Column("id", sa.String(), nullable=False),
    sa.Column("scope", sa.String(), nullable=False),
    sa.Column("generated_by", sa.String(), nullable=False),
    sa.Column("content", sa.JSON(), nullable=False),
    sa.Column("created_at", sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint("id")
    )
    op.create_table("resource",
    sa.Column("id", sa.String(), nullable=False),
    sa.Column("skill", sa.String(), nullable=False),
    sa.Column("capacity", sa.Float(), nullable=False),
    sa.PrimaryKeyConstraint("id")
    )
    op.create_table("approval",
    sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
    sa.Column("message_id", sa.String(), nullable=False),
    sa.Column("approver", sa.String(), nullable=True),
    sa.Column("decision", sa.String(), nullable=False),
    sa.Column("decided_at", sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(["message_id"], ["agent_message.message_id"], ),
    sa.PrimaryKeyConstraint("id")
    )
    op.create_table("project",
    sa.Column("id", sa.String(), nullable=False),
    sa.Column("portfolio_id", sa.String(), nullable=False),
    sa.Column("skill", sa.String(), nullable=False),
    sa.Column("planned_start", sa.String(), nullable=True),
    sa.Column("planned_finish", sa.String(), nullable=True),
    sa.Column("deadline", sa.String(), nullable=True),
    sa.Column("status", sa.String(), nullable=False),
    sa.ForeignKeyConstraint(["portfolio_id"], ["portfolio.id"], ),
    sa.PrimaryKeyConstraint("id")
    )
    op.create_table("allocation",
    sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
    sa.Column("project_id", sa.String(), nullable=False),
    sa.Column("resource_id", sa.String(), nullable=False),
    sa.Column("week", sa.String(), nullable=False),
    sa.Column("hours", sa.Float(), nullable=False),
    sa.ForeignKeyConstraint(["project_id"], ["project.id"], ),
    sa.ForeignKeyConstraint(["resource_id"], ["resource.id"], ),
    sa.PrimaryKeyConstraint("id")
    )
    op.create_table("risk",
    sa.Column("id", sa.String(), nullable=False),
    sa.Column("project_id", sa.String(), nullable=False),
    sa.Column("signal", sa.Text(), nullable=False),
    sa.Column("severity", sa.String(), nullable=False),
    sa.Column("detected_at", sa.DateTime(), nullable=True),
    sa.Column("materialized_at", sa.DateTime(), nullable=True),
    sa.Column("mitigation", sa.Text(), nullable=False),
    sa.ForeignKeyConstraint(["project_id"], ["project.id"], ),
    sa.PrimaryKeyConstraint("id")
    )
    op.create_table("task",
    sa.Column("id", sa.String(), nullable=False),
    sa.Column("project_id", sa.String(), nullable=False),
    sa.Column("wbs", sa.String(), nullable=False),
    sa.Column("effort", sa.Float(), nullable=False),
    sa.Column("deps", sa.JSON(), nullable=False),
    sa.Column("percent_complete", sa.Float(), nullable=False),
    sa.ForeignKeyConstraint(["project_id"], ["project.id"], ),
    sa.PrimaryKeyConstraint("id")
    )


def downgrade() -> None:
    op.drop_table("task")
    op.drop_table("risk")
    op.drop_table("allocation")
    op.drop_table("project")
    op.drop_table("approval")
    op.drop_table("resource")
    op.drop_table("report")
    op.drop_table("portfolio")
    op.drop_table("kpi_event")
    op.drop_table("knowledge_doc")
    op.drop_table("agent_message")
