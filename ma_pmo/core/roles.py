"""Roles (RACI) per decision kind and project (roadmap 9, step 4; MADR, ISO 21502 7.12).

For each kind of decision (gate, budget, allocation, question, ..., or `*` for all) and each
project (or all projects), people are Responsible, Accountable, Consulted or Informed:

- an approval goes to the Accountable people: once someone is A, only they can decide it;
- the Consulted are asked, and the Informed are told, through the approval's notifications;
- a decision record names them (decision makers, consulted, informed);
- a commitment is owed by R to A (a question is asked of R), and its escalation goes to A.

The most specific assignment wins: this kind and this project, then this kind in every
project, then every kind in this project, then every kind everywhere. With nobody assigned,
today's behaviour applies: anyone with the approver role decides.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from ma_pmo.core.i18n import tr
from ma_pmo.core.times import iso
from ma_pmo.db.models import RoleAssignment
from ma_pmo.db.session import get_session

ROLES = ("R", "A", "C", "I")
ANY = "*"


class NotAccountable(PermissionError):
    """Someone who is not Accountable for a decision tried to decide it."""


def _row(r: RoleAssignment) -> dict[str, Any]:
    return {"id": r.id, "kind": r.kind, "project_id": r.project_id or None, "role": r.role,
            "person": r.person, "created_by": r.created_by, "created_at": iso(r.created_at)}


def assign(kind: str, role: str, person: str, *, project: str | None = None,
           by: str = "") -> dict[str, Any]:
    """Give `person` a role; assigning the same role twice is a no-op."""
    role, person, kind = role.upper(), person.strip(), (kind or "").strip()
    if role not in ROLES:
        raise ValueError(tr("role must be R, A, C or I", "역할은 R, A, C, I 중 하나여야 합니다"))
    if not person or not kind:
        raise ValueError(tr("a role needs a kind and a person",
                            "역할에는 종류와 사람이 필요합니다"))
    with get_session() as s:
        same = s.scalars(select(RoleAssignment).where(
            RoleAssignment.kind == kind, RoleAssignment.project_id == (project or ""),
            RoleAssignment.role == role, RoleAssignment.person == person)).first()
        if same is not None:
            return _row(same)
        row = RoleAssignment(kind=kind, project_id=project or "", role=role, person=person,
                             created_by=by)
        s.add(row)
        try:
            s.flush()
        except IntegrityError:  # assigned at the same moment by someone else
            raise ValueError(tr("already assigned", "이미 지정되어 있습니다")) from None
        return _row(row)


def remove(assignment_id: int) -> bool:
    with get_session() as s:
        gone = s.execute(delete(RoleAssignment).where(RoleAssignment.id == assignment_id))
        return bool(gone.rowcount)  # type: ignore[attr-defined]


def list_roles(kind: str | None = None, project: str | None = None) -> list[dict[str, Any]]:
    with get_session() as s:
        q = select(RoleAssignment).order_by(RoleAssignment.kind, RoleAssignment.project_id,
                                            RoleAssignment.role, RoleAssignment.person)
        if kind:
            q = q.where(RoleAssignment.kind == kind)
        if project is not None:
            q = q.where(RoleAssignment.project_id == project)
        return [_row(r) for r in s.scalars(q).all()]


def who(kind: str, role: str, project: str | None = None) -> list[str]:
    """The people with `role` for this kind of decision in this project; the most specific
    assignment wins. Empty when nobody is assigned."""
    with get_session() as s:
        rows = s.scalars(select(RoleAssignment).where(
            RoleAssignment.role == role, RoleAssignment.kind.in_((kind, ANY)),
            RoleAssignment.project_id.in_((project or "", "")))).all()
    for k, p in ((kind, project or ""), (kind, ""), (ANY, project or ""), (ANY, "")):
        found = sorted(r.person for r in rows if r.kind == k and r.project_id == p)
        if found:
            return found
    return []


def raci(kind: str, project: str | None = None) -> dict[str, list[str]]:
    return {role: who(kind, role, project) for role in ROLES}


def check_accountable(kind: str, project: str | None, person: str) -> None:
    """NotAccountable unless nobody is A for this decision, or `person` is."""
    accountable = who(kind, "A", project)
    if accountable and person not in accountable:
        raise NotAccountable(tr(
            f"only {', '.join(accountable)} can decide this ({kind}"
            f"{', ' + project if project else ''})",
            f"이 결정({kind}{', ' + project if project else ''})은 "
            f"{', '.join(accountable)}만 내릴 수 있습니다"))
