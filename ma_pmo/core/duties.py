"""Segregation of duties (roadmap 10, step 4; NIST AI RMF GOVERN, ISO/IEC 42001 Annex A).

The `segregation` guardrail (point `decision`; `enforce` by default since the evaluation in
docs/GUARDRAILS-EVAL.md) checks each approval:

- nobody approves or rejects their own request: a run records who asked for it
  (`requested_by`, the authenticated user who started the scenario or goal), and that person
  cannot decide its outputs;
- an agent never decides: agent ids (A1-A8, plugins) and system actors cannot be approvers;
- above a threshold two people approve: decisions of the kinds in `two_person_kinds`, risks
  rated in `two_person_severities` (default `critical`), and tolerance exceptions
  (`two_person_exceptions`, default on). The first approval is kept as a sign-off and the item
  stays in the queue; a second, different person completes it. One rejection is enough.

That the agent which built a decision cannot be its only reviewer already holds: review needs
the dedicated A8 step (docs/REVIEW.md).
"""
from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

from ma_pmo.core.guardrails import ALLOW, ASK, BLOCK, ENFORCE, Result, register

SYSTEM_ACTORS = {"due-dates", "tracker", "scheduler", "system"}
_requester: ContextVar[str | None] = ContextVar("ma_pmo_requester", default=None)


@contextmanager
def requested_by(person: str | None) -> Iterator[None]:
    """Who is asking for the runs started inside the block (an authenticated user)."""
    token = _requester.set(person)
    try:
        yield
    finally:
        _requester.reset(token)


def requester() -> str | None:
    return _requester.get()


def _agents() -> set[str]:
    from ma_pmo.agents.registry import WORKERS

    return {"A1", *WORKERS.keys()}


def two_people(context: dict[str, Any], params: dict[str, Any]) -> bool:
    """Whether this decision needs a second approver."""
    if context.get("kind") in (params.get("two_person_kinds") or []):
        return True
    if context.get("severity") in (params.get("two_person_severities") or []):
        return True
    return bool(params.get("two_person_exceptions")) and bool(context.get("exception"))


@register("segregation", "decision", ENFORCE,
          "No self-approval, agents never approve, two approvers above a threshold",
          two_person_kinds=[], two_person_severities=["critical"], two_person_exceptions=True)
def _check(context: dict[str, Any], params: dict[str, Any]) -> Result:
    who, asker = context["approver"], context.get("requested_by")
    seen = {"approver": who, "decision": context["decision"], "kind": context.get("kind"),
            "requested_by": asker}
    if who in _agents() or who in SYSTEM_ACTORS:
        return Result(BLOCK, f"{who} is an agent or system actor: only people decide",
                      detail=seen)
    if asker and who == asker:
        return Result(BLOCK, f"{who} asked for this run and cannot decide its own request",
                      detail=seen)
    if context["decision"] != "approve" or not two_people(context, params):
        return Result(ALLOW, "duties separated", detail=seen)
    signed = [s["who"] for s in context.get("signoffs") or []]
    if who in signed:
        return Result(BLOCK, f"{who} already signed off: the second approval needs someone else",
                      detail={**seen, "signoffs": signed})
    if not signed:
        return Result(ASK, "a second approver is needed", detail={**seen, "signoffs": signed})
    return Result(ALLOW, f"second approval, after {', '.join(signed)}",
                  detail={**seen, "signoffs": signed})


class NotSeparated(PermissionError):
    """The approval breaks segregation of duties (an enforced `segregation` guardrail)."""
