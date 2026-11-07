"""Workflow versions: one validator, immutable drafts, and published versions per workspace.

The workflows that ship with MA-PMO, and those in `MA_PMO_WORKFLOWS_DIR`, are the base. A
workspace changes one by saving a draft (a new version number; the spec never changes after)
and publishing it; the latest published version is the one that runs there. Every version stays
readable, and every run keeps the spec it started with (see core/runs.py).

`problems` is the only validator: the API, the CLI and the dashboard all go through it. On top of
the spec's own rules (unique steps, known dependencies, no cycles) it checks that agents exist,
that every gate step is required, and that a required step of the workflow in use is neither
removed nor changed.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from ma_pmo.agents import registry
from ma_pmo.core.i18n import tr
from ma_pmo.core.workflow import WorkflowSpec
from ma_pmo.db.models import WorkflowVersion
from ma_pmo.db.session import get_session

DRAFT, PUBLISHED = "draft", "published"


class Invalid(ValueError):
    """The spec breaks a rule; `problems` says which."""

    def __init__(self, problems: list[str]) -> None:
        super().__init__("; ".join(problems))
        self.problems = problems


def published(workflow_id: str) -> WorkflowSpec | None:
    """The latest published version in this workspace, if there is one."""
    with get_session() as s:
        row = s.scalars(select(WorkflowVersion).where(
            WorkflowVersion.workflow_id == workflow_id, WorkflowVersion.status == PUBLISHED)
            .order_by(WorkflowVersion.version.desc()).limit(1)).first()
        return WorkflowSpec.model_validate(row.spec) if row else None


def published_all() -> dict[str, WorkflowSpec]:
    """Every workflow with a published version in this workspace, at its latest one."""
    with get_session() as s:
        rows = s.scalars(select(WorkflowVersion).where(WorkflowVersion.status == PUBLISHED)
                         .order_by(WorkflowVersion.version)).all()
        return {r.workflow_id: WorkflowSpec.model_validate(r.spec) for r in rows}


def problems(data: dict[str, Any], workflow_id: str | None = None,
             ) -> tuple[WorkflowSpec | None, list[str]]:
    """The spec, and every rule it breaks (none means it can be saved and published)."""
    from ma_pmo.core import scenarios

    try:
        spec = WorkflowSpec.model_validate(data)
    except ValidationError as e:
        return None, [f"{'.'.join(map(str, err['loc'])) or 'spec'}: {err['msg']}"
                      for err in e.errors()]
    found: list[str] = []
    if workflow_id is not None and spec.id != workflow_id:
        found.append(tr(f"id '{spec.id}' does not match the workflow '{workflow_id}'",
                        f"id '{spec.id}'가 워크플로 '{workflow_id}'와 다릅니다"))
    if spec.ablated:
        found.append(tr("an ablated workflow is an experiment and cannot be saved",
                        "에이전트를 뺀 실험용 워크플로는 저장할 수 없습니다"))
    if spec.category not in scenarios.CATEGORIES:
        allowed = ", ".join(scenarios.CATEGORIES)
        found.append(tr(f"unknown category '{spec.category}': use one of {allowed}",
                        f"없는 분류입니다: '{spec.category}' (가능: {allowed})"))
    unknown = sorted({s.agent for s in spec.steps} - set(registry.specs()))
    if unknown:
        found.append(tr(f"unknown agents: {', '.join(unknown)}",
                        f"없는 에이전트입니다: {', '.join(unknown)}"))
    for step in spec.steps:
        if "gate" in step.params and not step.required:
            found.append(tr(f"step '{step.id}' is a gate and must be required",
                            f"단계 '{step.id}'는 게이트이므로 필수여야 합니다"))
    try:
        in_use = scenarios.workflow(spec.id)
    except KeyError:
        in_use = None
    new = {s.id: s for s in spec.steps}
    for step in in_use.steps if in_use else []:
        if not step.required:
            continue
        kept = new.get(step.id)
        if kept is None:
            found.append(tr(f"required step '{step.id}' ({step.agent}) cannot be removed",
                            f"필수 단계 '{step.id}'({step.agent})는 뺄 수 없습니다"))
        elif (kept.agent, kept.params, kept.required) != (step.agent, step.params, True):
            found.append(tr(f"required step '{step.id}' ({step.agent}) cannot be changed",
                            f"필수 단계 '{step.id}'({step.agent})는 바꿀 수 없습니다"))
    return spec, found


def _next_version(s: Any, workflow_id: str) -> int:
    from ma_pmo.core import scenarios

    saved = s.scalar(select(func.max(WorkflowVersion.version)).where(
        WorkflowVersion.workflow_id == workflow_id)) or 0
    try:
        base = scenarios.loaded(workflow_id).version
    except KeyError:
        base = 0
    return max(saved, base) + 1


def save_draft(data: dict[str, Any], author: str, note: str = "",
               workflow_id: str | None = None) -> dict:
    """Validate and store a new draft version. Raises Invalid."""
    spec, found = problems(data, workflow_id)
    if found or spec is None:
        raise Invalid(found)
    with get_session() as s:
        version = _next_version(s, spec.id)
        row = WorkflowVersion(workflow_id=spec.id, version=version,
                              spec=spec.model_copy(update={"version": version}).model_dump(),
                              status=DRAFT, note=note, created_by=author)
        s.add(row)
        try:
            s.flush()
        except IntegrityError:  # someone saved the same version a moment ago
            raise Invalid([tr(
                f"version {version} of '{spec.id}' was just saved: try again",
                f"'{spec.id}' 버전 {version}이 방금 저장되었습니다. 다시 시도하세요")]) from None
        return _row(row)


def publish(workflow_id: str, version: int, by: str) -> dict:
    """Make a draft the version in use. KeyError if missing; Invalid if it no longer passes."""
    with get_session() as s:
        row = s.scalar(select(WorkflowVersion).where(
            WorkflowVersion.workflow_id == workflow_id, WorkflowVersion.version == version))
        if row is None:
            raise KeyError(f"{workflow_id} v{version}")
        if row.status != DRAFT:
            raise Invalid([tr(f"version {version} is already {row.status}",
                              f"버전 {version}은 이미 {row.status} 상태입니다")])
        spec = dict(row.spec)
    _, found = problems(spec, workflow_id)  # the version in use may have changed since
    if found:
        raise Invalid(found)
    with get_session() as s:
        row = s.scalar(select(WorkflowVersion).where(
            WorkflowVersion.workflow_id == workflow_id, WorkflowVersion.version == version))
        assert row is not None
        row.status, row.published_by, row.published_at = PUBLISHED, by, datetime.now(UTC)
        return _row(row)


def versions(workflow_id: str) -> list[dict]:
    """Every version, oldest first: the shipped or file base, then this workspace's own."""
    from ma_pmo.core import scenarios
    from ma_pmo.core.workflow import builtin_ids

    out: list[dict] = []
    try:
        base = scenarios.loaded(workflow_id)
        out.append({"version": base.version,
                    "status": "builtin" if workflow_id in builtin_ids() else "file",
                    "note": "", "created_by": None, "created_at": None,
                    "published_by": None, "published_at": None})
    except KeyError:
        pass
    with get_session() as s:
        rows = s.scalars(select(WorkflowVersion).where(WorkflowVersion.workflow_id == workflow_id)
                         .order_by(WorkflowVersion.version)).all()
        out += [_row(r) for r in rows]
    try:
        in_use = scenarios.workflow(workflow_id).version
    except KeyError:
        in_use = None
    return [{**v, "in_use": v["version"] == in_use} for v in out]


def spec_of(workflow_id: str, version: int) -> WorkflowSpec:
    """One version's spec, old ones included. KeyError if there is none."""
    from ma_pmo.core import scenarios

    with get_session() as s:
        row = s.scalar(select(WorkflowVersion).where(
            WorkflowVersion.workflow_id == workflow_id, WorkflowVersion.version == version))
        if row is not None:
            return WorkflowSpec.model_validate(row.spec)
    base = scenarios.loaded(workflow_id)
    if base.version != version:
        raise KeyError(f"{workflow_id} v{version}")
    return base


def _row(r: WorkflowVersion) -> dict:
    return {"version": r.version, "status": r.status, "note": r.note,
            "created_by": r.created_by,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "published_by": r.published_by,
            "published_at": r.published_at.isoformat() if r.published_at else None}
