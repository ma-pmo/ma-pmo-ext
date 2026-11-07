"""Workspaces: every row belongs to one, and chosen ids are unique per workspace.

Existing rows move into the `default` workspace. Portfolio, project, task, resource and
knowledge ids get a (workspace_id, id) key, and the references to them become composite, so a
row cannot point into another workspace.

Constraint names follow Postgres' defaults (`task_pkey`, `task_project_id_fkey`). Baseline
constraints were unnamed; on SQLite the same names are given to them through the batch naming
convention, so one set of operations runs on both.

Revision ID: 0005_workspaces
Revises: 0004_plan_start
"""
from __future__ import annotations

from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

revision = "0005_workspaces"
down_revision = "0004_plan_start"
branch_labels = None
depends_on = None

DEFAULT = "default"
NAMES = {"fk": "%(table_name)s_%(column_0_name)s_fkey", "pk": "%(table_name)s_pkey"}
TABLES = ("portfolio", "project", "task", "resource", "allocation", "risk", "report", "run",
          "run_step", "agent_message", "approval", "knowledge_doc", "kpi_event")
KEYED = ("portfolio", "project", "resource", "task", "knowledge_doc")  # parents first
REFS = (  # (table, column, referenced table)
    ("project", "portfolio_id", "portfolio"),
    ("task", "project_id", "project"),
    ("allocation", "project_id", "project"),
    ("allocation", "resource_id", "resource"),
    ("risk", "project_id", "project"),
)


def _batch(table: str):  # type: ignore[no-untyped-def]
    return op.batch_alter_table(table, naming_convention=NAMES)


def upgrade() -> None:
    op.create_table(
        "workspace",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.bulk_insert(sa.table("workspace", sa.column("id"), sa.column("name"),
                            sa.column("created_at", sa.DateTime())),
                   [{"id": DEFAULT, "name": "Default", "created_at": datetime.now(UTC)}])
    for table in TABLES:
        with _batch(table) as batch:
            batch.add_column(sa.Column("workspace_id", sa.String(), nullable=True))
        op.execute(sa.text(f"UPDATE {table} SET workspace_id = :w").bindparams(w=DEFAULT))
        with _batch(table) as batch:
            batch.alter_column("workspace_id", existing_type=sa.String(), nullable=False)
            batch.create_index(f"ix_{table}_workspace_id", ["workspace_id"])
            batch.create_foreign_key(f"{table}_workspace_id_fkey", "workspace",
                                     ["workspace_id"], ["id"])
    for table, column, _ in REFS:  # children let go of their parents' old keys...
        with _batch(table) as batch:
            batch.drop_constraint(f"{table}_{column}_fkey", type_="foreignkey")
    for table in KEYED:  # ...the parents take composite keys...
        with _batch(table) as batch:
            batch.drop_constraint(f"{table}_pkey", type_="primary")
            batch.create_primary_key(f"{table}_pkey", ["workspace_id", "id"])
    for table, column, parent in REFS:  # ...and the children point at them again
        with _batch(table) as batch:
            batch.create_foreign_key(f"{table}_{column}_fkey", parent,
                                     ["workspace_id", column], ["workspace_id", "id"])


def downgrade() -> None:
    """Only a database with nothing outside `default` can go back."""
    bind = op.get_bind()
    for table in TABLES:
        others = bind.execute(sa.text(f"SELECT COUNT(*) FROM {table} WHERE workspace_id <> :w")
                              .bindparams(w=DEFAULT)).scalar_one()
        if others:
            raise RuntimeError(f"{table} has rows outside the default workspace")
    for table, column, _ in REFS:
        with _batch(table) as batch:
            batch.drop_constraint(f"{table}_{column}_fkey", type_="foreignkey")
    for table in KEYED:
        with _batch(table) as batch:
            batch.drop_constraint(f"{table}_pkey", type_="primary")
            batch.create_primary_key(f"{table}_pkey", ["id"])
    for table, column, parent in REFS:
        with _batch(table) as batch:
            batch.create_foreign_key(f"{table}_{column}_fkey", parent, [column], ["id"])
    for table in TABLES:
        with _batch(table) as batch:
            batch.drop_constraint(f"{table}_workspace_id_fkey", type_="foreignkey")
            batch.drop_index(f"ix_{table}_workspace_id")
            batch.drop_column("workspace_id")
    op.drop_table("workspace")
