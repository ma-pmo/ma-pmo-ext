"""Policy as data: each guardrail's mode and parameters per workspace, versioned (roadmap 10).

A policy is a document `{"guardrails": {name: {"mode": ..., "params": {...}}}}`. Every change
is a new version (who, when, why) and a decision record (kind `policy`); the highest version is
in force, and with none the built-in defaults apply as version 0. A run stores the version it
started under (`policy_version` in its state).
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from ma_pmo.core import guardrails
from ma_pmo.core.i18n import tr
from ma_pmo.core.times import iso
from ma_pmo.db.models import Policy
from ma_pmo.db.session import get_session


def _latest() -> Policy | None:
    with get_session() as s:
        row = s.scalars(select(Policy).order_by(Policy.version.desc())).first()
        if row is not None:
            s.expunge(row)
        return row


def version() -> int:
    row = _latest()
    return row.version if row is not None else 0


def setting(name: str) -> tuple[str, dict[str, Any], int]:
    """(mode, params, policy version) for one guardrail."""
    row = _latest()
    chosen = ((row.document if row else {}).get("guardrails") or {}).get(name) or {}
    default = guardrails.REGISTRY[name].default_mode
    return chosen.get("mode", default), chosen.get("params") or {}, row.version if row else 0


def current() -> dict[str, Any]:
    """The policy in force, with every guardrail filled in from the defaults."""
    row = _latest()
    chosen = (row.document if row else {}).get("guardrails") or {}
    return {
        "version": row.version if row else 0,
        "created_by": row.created_by if row else None,
        "created_at": iso(row.created_at) if row else None,
        "note": row.note if row else "",
        "tolerances": (row.document if row else {}).get("tolerances") or {},
        "guardrails": [{**g, "mode": (chosen.get(g["name"]) or {}).get("mode", g["default_mode"]),
                        "params": {**g["params"],
                                   **((chosen.get(g["name"]) or {}).get("params") or {})}}
                       for g in guardrails.catalog()],
    }


def versions() -> list[dict[str, Any]]:
    with get_session() as s:
        return [{"version": r.version, "document": r.document, "note": r.note,
                 "created_by": r.created_by, "created_at": iso(r.created_at)}
                for r in s.scalars(select(Policy).order_by(Policy.version.desc())).all()]


def change(settings: dict[str, dict[str, Any]], *, by: str, note: str = "",
           tolerances: dict[str, Any] | None = None) -> dict[str, Any]:
    """A new version with these guardrails changed ({name: {mode, params}}) and, if given, the
    tolerances replaced; the rest carry over. ValueError for an unknown guardrail or mode, or
    tolerances that are unknown or widen a level above."""
    from ma_pmo.core import tolerances as tol

    if tolerances is not None:
        tol.validate(tolerances)
    guardrails.catalog()  # every guardrail registered
    for name, value in settings.items():
        if name not in guardrails.REGISTRY:
            raise ValueError(tr(f"unknown guardrail: {name}", f"없는 가드레일입니다: {name}"))
        if value.get("mode", guardrails.OFF) not in guardrails.MODES:
            raise ValueError(tr(f"mode must be one of {guardrails.MODES}",
                                f"모드는 {guardrails.MODES} 중 하나여야 합니다"))
    row = _latest()
    merged = dict((row.document if row else {}).get("guardrails") or {})
    for name, value in settings.items():
        merged[name] = {**merged.get(name, {}), **value}
    with get_session() as s:
        number = (s.scalar(select(func.max(Policy.version))) or 0) + 1
        document: dict[str, Any] = {"guardrails": merged}
        kept = tolerances if tolerances is not None else (row.document if row else {}).get(
            "tolerances")
        if kept:
            document["tolerances"] = kept
        s.add(Policy(version=number, document=document, note=note, created_by=by))
        try:
            s.flush()
        except IntegrityError:  # changed at the same moment by someone else
            raise ValueError(tr("the policy just changed: try again",
                                "정책이 방금 바뀌었습니다. 다시 시도하세요")) from None
    from ma_pmo.core import decisions

    summary = ", ".join([f"{n}: {v.get('mode', '')}".rstrip(": ") for n, v in settings.items()]
                        + (["tolerances"] if tolerances is not None else []))
    decisions.by_person("policy", "policy", tr(f"policy v{number}: {summary}",
                                               f"정책 v{number}: {summary}"),
                        by, f"v{number}", rationale=note or None)
    return current()
