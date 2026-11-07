"""Postgres row-level security: the database itself keeps workspaces apart.

The second line behind the ORM filter (`ma_pmo/db/session.py`). Each transaction tells
Postgres its workspace with `set_config('ma_pmo.workspace', …, true)`; rows of other workspaces
are invisible and cannot be written. Work that must see everything (recovery, migrations) sets
`ma_pmo.all_workspaces` to `on` for that statement or transaction.

FORCE applies the policies to the table owner too, which is usually the role the API connects
as. Superusers and roles with BYPASSRLS are never subject to RLS: connect as an ordinary role.
SQLite has no RLS; there the ORM filter is the only line.

Revision ID: 0007_row_level_security
Revises: 0006_memberships
"""
from __future__ import annotations

from alembic import op

revision = "0007_row_level_security"
down_revision = "0006_memberships"
branch_labels = None
depends_on = None

TABLES = ("portfolio", "project", "task", "resource", "allocation", "risk", "report", "run",
          "run_step", "agent_message", "approval", "knowledge_doc", "kpi_event")
RULE = ("current_setting('ma_pmo.all_workspaces', true) = 'on' "
        "OR workspace_id = current_setting('ma_pmo.workspace', true)")


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    for table in TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(f"CREATE POLICY workspace_isolation ON {table} USING ({RULE}) "
                   f"WITH CHECK ({RULE})")


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    for table in TABLES:
        op.execute(f"DROP POLICY IF EXISTS workspace_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
