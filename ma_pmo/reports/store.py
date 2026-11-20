"""Stored reports: list them, read one, and read reports stored before report.v2."""
from __future__ import annotations

from typing import Any

from sqlalchemy import select

from ma_pmo.core.schemas.payloads.report_v2 import ReportV2
from ma_pmo.core.times import iso
from ma_pmo.db.models import Report
from ma_pmo.db.session import get_session

_RANK = {"green": 0, "amber": 1, "red": 2}


def as_v2(content: dict[str, Any], created: str) -> dict[str, Any] | None:
    """`content` as report.v2. A report.v1 row becomes a status report without facts; anything
    else (a row no version of A5 wrote) is None."""
    if "facts" in content:
        return content
    if "executive_summary" not in content:
        return None
    lines = content.get("project_status", [])
    worst = max((p.get("status", "green") for p in lines), key=_RANK.__getitem__,
                default="green")
    return ReportV2.model_validate({
        **content, "kind": "status", "path": "llm", "overall_status": worst,
        "facts": {"as_of": created[:10]},
    }).model_dump()


def _summary(row: Report) -> dict[str, Any] | None:
    c = as_v2(row.content, iso(row.created_at) or "")
    if c is None:
        return None
    return {"id": row.id, "scope": row.scope, "kind": c.get("kind", "status"),
            "title": c.get("title", ""), "as_of": c["facts"]["as_of"],
            "language": c.get("language", "en"),
            "overall_status": c["overall_status"], "path": c["path"],
            "projects": c["facts"].get("projects_in_scope"),
            "created_at": iso(row.created_at)}


def list_reports(scope: str | None = None, kind: str | None = None,
                 limit: int = 50) -> list[dict[str, Any]]:
    """Newest first, in the current workspace."""
    with get_session() as s:
        q = select(Report).order_by(Report.created_at.desc())
        if scope:
            q = q.where(Report.scope == scope)
        rows = s.scalars(q.limit(limit if not kind else 1000)).all()
        out = [x for x in (_summary(r) for r in rows) if x is not None]
    return [r for r in out if not kind or r["kind"] == kind][:limit]


def get_report(report_id: str) -> dict[str, Any] | None:
    """The report as report.v2 content, or None."""
    with get_session() as s:
        row = s.scalars(select(Report).where(Report.id == report_id)).first()
        if row is None:
            return None
        return as_v2(dict(row.content), iso(row.created_at) or "")


def latest(scope: str | None = None, kind: str | None = None) -> tuple[str, dict] | None:
    rows = list_reports(scope, kind, limit=1)
    if not rows:
        return None
    content = get_report(rows[0]["id"])
    return (rows[0]["id"], content) if content else None
