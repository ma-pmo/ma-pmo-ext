"""Commit gate: a reviewed run's decisions take effect only once their reviews hold.

At the end of a run of a workflow with `"review": true`, every decision on the board (each
gate_review.v1 and report.v1) is checked:

- no reviewer CHALLENGEs it, and
- every constraint that applies to it has a VERIFIED verdict from the dedicated reviewer (A8).
  A constraint applies when the agent it rests on ran in this run (A4 for risks, A3 for staffing
  and allocation). A builder that could not read that agent posts no verdict for it; a builder
  that could and challenged it blocks the commit like any other challenge.

A challenged decision also needs at least one ALTERNATIVE on the board, so the person deciding
sees another course next to the challenge; without one, `alternative` is reported missing.

A decision that meets both is `committed`. Any other is `review_pending`: it goes to the approval
queue, with the challenges, their evidence and what was not checked attached, so the person who
decides sees both sides. A decision that already needed approval keeps its one approval, which
gains the same detail. Passing review never replaces an approval that was required anyway.

This is ArcticSwarm's commit gate (Yoon et al., 2026, arXiv:2609.01870, Section 3 and Appendix
G.1.2), implemented independently and changed for project decisions in two ways: an unmet
condition goes to a person instead of becoming advisory at a deadline, and missing reviews are
reported rather than spawned, so a run stays the static, resumable workflow it started as.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import select

from ma_pmo.core import board, runs
from ma_pmo.core.obs import get_logger
from ma_pmo.core.workflow import AUDITOR, WorkflowSpec
from ma_pmo.db.models import Approval
from ma_pmo.db.session import get_session

_log = get_logger("commit")
COMMITTED, REVIEW_PENDING = "committed", "review_pending"
CANDIDATES = {"gate_review.v1", "report.v1"}
# constraint -> the agent whose posts it rests on
SOURCES = {"gate.no_open_high_risk": "A4", "gate.staffed": "A3",
           "gate.allocation_by_deadline": "A3", "report.covers_risks": "A4"}
APPLIES_TO = {"gate_review.v1": ("gate.no_open_high_risk", "gate.staffed",
                                 "gate.allocation_by_deadline"),
              "report.v1": ("report.covers_risks",)}


def check(run_id: str, spec: WorkflowSpec) -> list[dict[str, Any]]:
    """Decide each decision of a reviewed run, queue the held ones, and record the outcome."""
    posts = board.posts(run_id, spec)
    reviews: dict[str, list[dict]] = {}
    for p in posts:
        if p["schema"] == "review.v1":
            reviews.setdefault(p["data"]["target"], []).append(p)
    ran = {s.agent for s in spec.steps}
    audited = AUDITOR in ran
    outcome = []
    for post in (p for p in posts if p["schema"] in CANDIDATES):
        mine = reviews.get(post["message_id"], [])
        applies = [c for c in APPLIES_TO[post["schema"]] if SOURCES[c] in ran]
        verified = {r["data"]["constraint"] for r in mine
                    if r["data"]["role"] == "dedicated" and r["data"]["verdict"] == "VERIFIED"}
        challenges = [r for r in mine if r["data"]["verdict"] == "CHALLENGE"]
        offered = [r for r in mine if r["data"]["verdict"] == "ALTERNATIVE"]
        judged = verified | {r["data"]["constraint"] for r in challenges}
        missing = [c for c in applies if c not in judged] if audited else ["review.dedicated"]
        if challenges and not offered:
            missing.append("alternative")
        status = COMMITTED if not challenges and not missing else REVIEW_PENDING
        outcome.append({
            "message_id": post["message_id"], "schema": post["schema"], "step": post["step"],
            "project_id": post["data"].get("project_id"), "status": status,
            "challenges": [r["message_id"] for r in challenges],
            "alternatives": [r["message_id"] for r in offered], "missing": missing})
    held = [o for o in outcome if o["status"] == REVIEW_PENDING]
    _queue(run_id, held)
    runs.update_state(run_id, commit=outcome)
    _log.info("commit_gate", run_id=run_id, decisions=len(outcome), held=len(held))
    return outcome


def _queue(run_id: str, held: list[dict]) -> None:
    """One pending approval per held decision, carrying why it is held."""
    with get_session() as s:
        for item in held:
            reason = {"kind": REVIEW_PENDING, "challenges": item["challenges"],
                      "alternatives": item["alternatives"], "missing": item["missing"]}
            approval = s.scalar(select(Approval).where(Approval.message_id == item["message_id"]))
            if approval is None:
                s.add(Approval(message_id=item["message_id"], decision="pending", run_id=run_id,
                               reason=reason))
            elif approval.decision == "pending":  # already asked for: say what review found
                approval.reason = reason


def held_detail(reason: dict | None, run_id: str | None, spec: WorkflowSpec | None,
                ) -> dict[str, Any] | None:
    """Why a decision is held, for the approver: challenges with rationale and evidence, the
    alternatives offered, and what nobody could check."""
    if not reason or reason.get("kind") != REVIEW_PENDING:
        return None
    by_id: dict[str, dict] = {}
    if run_id and spec is not None:
        by_id = {p["message_id"]: p for p in board.posts(run_id, spec)}

    def entries(ids: list[str], keys: tuple[str, ...]) -> list[dict]:
        return [{"agent": by_id[i]["agent"], **{k: by_id[i]["data"].get(k) for k in keys}}
                for i in ids if i in by_id]

    return {"kind": REVIEW_PENDING,
            "challenges": entries(reason.get("challenges", []),
                                  ("constraint", "verdict", "role", "rationale", "evidence")),
            "alternatives": entries(reason.get("alternatives", []),
                                    ("constraint", "alternative", "evidence")),
            "missing": reason.get("missing", [])}
