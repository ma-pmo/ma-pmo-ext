"""Workspaces and memberships: create them, grant roles, and look them up for a request.

Memberships live in the database and add to the roles an authenticator gives (see
`ma_pmo/api/auth.py`). A principal is a key name or a custom authenticator's subject.
"""
from __future__ import annotations

from sqlalchemy import delete, select

from ma_pmo.core.workspace import ROLES
from ma_pmo.db.models import Membership, Workspace
from ma_pmo.db.session import get_session


def exists(workspace_id: str) -> bool:
    with get_session() as s:
        return s.get(Workspace, workspace_id) is not None


def create(workspace_id: str, name: str = "") -> None:
    """Raises ValueError if it exists or the id is not usable in a header."""
    if not workspace_id or not workspace_id.isascii() or any(c.isspace() for c in workspace_id):
        raise ValueError(f"workspace id must be ASCII without spaces: {workspace_id!r}")
    with get_session() as s:
        if s.get(Workspace, workspace_id) is not None:
            raise ValueError(f"workspace '{workspace_id}' exists")
        s.add(Workspace(id=workspace_id, name=name or workspace_id))


def list_all() -> list[dict]:
    with get_session() as s:
        return [{"id": w.id, "name": w.name}
                for w in s.scalars(select(Workspace).order_by(Workspace.id))]


def grant(workspace_id: str, principal: str, role: str) -> bool:
    """False if the principal already had the role there."""
    if role not in ROLES:
        raise ValueError(f"role must be one of {', '.join(ROLES)}")
    if not exists(workspace_id):
        raise ValueError(f"unknown workspace '{workspace_id}'")
    with get_session() as s:
        found = s.scalar(select(Membership).where(
            Membership.workspace_id == workspace_id, Membership.principal == principal,
            Membership.role == role))
        if found is not None:
            return False
        s.add(Membership(workspace_id=workspace_id, principal=principal, role=role))
        return True


def revoke(workspace_id: str, principal: str, role: str) -> bool:
    with get_session() as s:
        result = s.execute(delete(Membership).where(
            Membership.workspace_id == workspace_id, Membership.principal == principal,
            Membership.role == role))
        return bool(result.rowcount)  # type: ignore[attr-defined]


def members(workspace_id: str) -> list[dict]:
    with get_session() as s:
        rows = s.scalars(select(Membership).where(Membership.workspace_id == workspace_id)
                         .order_by(Membership.principal, Membership.role))
        return [{"principal": m.principal, "role": m.role} for m in rows]


def memberships_of(principal: str) -> dict[str, frozenset[str]]:
    """Every workspace where the principal has a membership, with the roles granted there."""
    found: dict[str, set[str]] = {}
    with get_session() as s:
        for where, role in s.execute(select(Membership.workspace_id, Membership.role).where(
                Membership.principal == principal)):
            found.setdefault(where, set()).add(role)
    return {where: frozenset(roles) for where, roles in found.items()}


def roles_in(workspace_id: str, principal: str) -> frozenset[str] | None:
    """The principal's granted roles there, or None if the workspace does not exist."""
    with get_session() as s:
        if s.get(Workspace, workspace_id) is None:
            return None
        return frozenset(s.scalars(select(Membership.role).where(
            Membership.workspace_id == workspace_id, Membership.principal == principal)))
