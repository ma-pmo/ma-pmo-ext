"""Guardrails: one engine and one record for every check at a control point (roadmap 10).

A guardrail is a check at a control point (`input`, `retrieval`, `execution`, `output`,
`decision`, `spend`; after NeMo Guardrails' rail types and the OpenAI Agents SDK's guardrails).
It answers `allow`, `modify` (e.g. masked), `ask` (a person decides) or `block`, with a reason.

Each guardrail runs in a mode the workspace's policy sets (core/policy.py):

- `off`: not run;
- `observe`: run and recorded, but `allow` takes effect, so a PMO sees what it would have done;
- `enforce`: run, recorded, and its answer takes effect.

Every result is kept as a `guardrail.v1` entry (table `guardrail_check`): the point, guardrail,
mode, what it found, what took effect, the reason, evidence and the policy version. The entries
sit next to the communication log rather than in it, so notification counts stay what they are.

Step 1 puts the existing checks behind the engine, in `enforce` so nothing changes: the LLM
budget (`spend`) and payload schemas (`output`). New guardrails start in `observe`.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select

from ma_pmo.core.obs import get_logger
from ma_pmo.core.times import iso
from ma_pmo.db.models import GuardrailCheck
from ma_pmo.db.session import get_session

_log = get_logger("guardrails")

ALLOW, MODIFY, ASK, BLOCK = "allow", "modify", "ask", "block"
OFF, OBSERVE, ENFORCE = "off", "observe", "enforce"
MODES = (OFF, OBSERVE, ENFORCE)
POINTS = ("input", "retrieval", "execution", "output", "decision", "spend")


@dataclass
class Result:
    decision: str
    reason: str = ""
    evidence: list[dict] = field(default_factory=list)
    detail: dict[str, Any] = field(default_factory=dict)  # recorded, except keys starting "_"
    value: Any = None  # for `modify`: the changed value
    error: BaseException | None = None  # for `block`: what the caller raises, if anything
    observed: str | None = None  # in observe mode: what the guardrail would have done


@dataclass
class Guardrail:
    name: str
    point: str
    default_mode: str
    description: str
    check: Callable[[dict[str, Any], dict[str, Any]], Result]  # (context, params) -> Result
    params: dict[str, Any] = field(default_factory=dict)  # defaults


REGISTRY: dict[str, Guardrail] = {}


def register(name: str, point: str, default_mode: str, description: str,
             **params: Any) -> Callable[[Callable], Callable]:
    """Declare a guardrail; its check takes (context, params) and returns a Result."""
    if point not in POINTS or default_mode not in MODES:
        raise ValueError(f"bad guardrail {name}: {point}/{default_mode}")

    def add(fn: Callable[[dict[str, Any], dict[str, Any]], Result]) -> Callable:
        REGISTRY[name] = Guardrail(name, point, default_mode, description, fn, params)
        return fn

    return add


def run(name: str, context: dict[str, Any], *, message_id: str | None = None) -> Result:
    """Run one guardrail under the policy in force; record it unless it is off."""
    from ma_pmo.core import policy
    from ma_pmo.core.runs import current_run_id

    guardrail = REGISTRY[name]
    mode, params, version = policy.setting(name)
    if mode == OFF:
        return Result(ALLOW, "off")
    found = guardrail.check(context, {**guardrail.params, **params})
    effective = found if mode == ENFORCE else Result(
        ALLOW, found.reason, found.evidence, found.detail,
        observed=found.decision if found.decision != ALLOW else None)
    _record(guardrail, mode, found, effective, version, current_run_id(), message_id)
    return effective


def _record(g: Guardrail, mode: str, found: Result, effective: Result, version: int,
            run_id: str | None, message_id: str | None) -> None:
    kept = {k: v for k, v in found.detail.items() if not k.startswith("_")}  # "_": in-process
    try:
        with get_session() as s:
            s.add(GuardrailCheck(
                name=g.name, point=g.point, mode=mode, decision=effective.decision,
                outcome=found.decision, reason=found.reason[:2000],
                detail={**kept, **({"evidence": found.evidence} if found.evidence else {})}
                or None,
                policy_version=version, run_id=run_id, message_id=message_id))
    except Exception as e:  # the record must not stop the work it checks
        _log.warning("guardrail_record_failed", guardrail=g.name, error=str(e)[:200])


def as_dict(row: GuardrailCheck) -> dict[str, Any]:
    return {"id": row.id, "name": row.name, "point": row.point, "mode": row.mode,
            "decision": row.decision, "outcome": row.outcome, "reason": row.reason,
            "detail": row.detail or {}, "policy_version": row.policy_version,
            "run_id": row.run_id, "message_id": row.message_id,
            "created_at": iso(row.created_at)}


def log(*, name: str | None = None, point: str | None = None, decision: str | None = None,
        outcome: str | None = None, run: str | None = None,
        limit: int = 200) -> list[dict[str, Any]]:
    """Recorded results, newest first. `outcome=block` in observe mode shows what would have
    been blocked."""
    with get_session() as s:
        q = select(GuardrailCheck).order_by(GuardrailCheck.id.desc())
        for column, value in ((GuardrailCheck.name, name), (GuardrailCheck.point, point),
                              (GuardrailCheck.decision, decision),
                              (GuardrailCheck.outcome, outcome),
                              (GuardrailCheck.run_id, run)):
            if value:
                q = q.where(column == value)
        return [as_dict(r) for r in s.scalars(q.limit(limit)).all()]


def catalog() -> list[dict[str, Any]]:
    """Every guardrail with its point, default mode, parameters and what it checks."""
    _load()
    return [{"name": g.name, "point": g.point, "default_mode": g.default_mode,
             "description": g.description, "params": g.params} for g in REGISTRY.values()]


def _load() -> None:
    """The modules that declare guardrails (imported for their `register` calls)."""
    from ma_pmo.core import budgets, duties, protocol, safety, tolerances  # noqa: F401
