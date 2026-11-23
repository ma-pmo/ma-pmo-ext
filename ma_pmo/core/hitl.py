"""Human-in-the-loop approval gate — paper §8 governance.

High-risk decisions (budget, scope, contracts, external communication) are final only
after passing a human approval gate.
- `protocol.publish` queues a pending approval (approval table) for a gated message
- a run started with `pause_on_gate` stops after the step that queued it (`waiting_approval`): the
  executor skips the later steps and keeps its `run_step` rows, so nothing is held in memory and
  a restart loses nothing (core/executor.py, not a LangGraph interrupt)
- `resolve` records the decision; approving the last pending item resumes the run
  (`executor.resume_run`), rejecting cancels it
- approval latency is measured as a KPI (cost axis)
"""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select

from ma_pmo.core import commitments, decisions, kpi, roles, runs
from ma_pmo.core.obs import get_logger
from ma_pmo.db.models import AgentMessageRow, Approval
from ma_pmo.db.session import get_session
from ma_pmo.integrations.dispatch import emit_later
from ma_pmo.integrations.events import approval_resolved_event

_log = get_logger("hitl")


def list_pending() -> list[dict]:
    """Pending approval items + a summary of the original message.

    An item a commit gate held (`review`) carries the challenges behind it, with their rationale
    and evidence, and the constraints nobody could check.
    """
    with get_session() as s:
        rows = s.execute(
            select(Approval, AgentMessageRow)
            .join(AgentMessageRow, Approval.message_id == AgentMessageRow.message_id)
            .where(Approval.decision == "pending")
        ).all()
        return [
            {
                "approval_id": a.id,
                "message_id": a.message_id,
                "sender": m.sender,
                "intent": m.intent,
                "task_ref": m.task_ref,
                "confidence": m.confidence,
                "payload": m.payload,
                "requested_at": m.timestamp.isoformat(),
                "review": _review(a),
                # reopened because an obligation the decision created was missed (roadmap 9)
                "reopened": a.reason if (a.reason or {}).get("kind") == "reopened" else None,
                "accountable": _accountable(m),
            }
            for a, m in rows
        ]


def _accountable(message: AgentMessageRow) -> list[str]:
    """Who may decide this item (roadmap 9 roles); empty when anyone with the role may."""
    kind, subject, _ = decisions.describe((message.payload or {}).get("schema"),
                                          (message.payload or {}).get("data") or {},
                                          message.task_ref)
    return roles.who(kind, "A", decisions._project_of(kind, subject))


def _review(approval: Approval) -> dict | None:
    from ma_pmo.core.commit import held_detail
    from ma_pmo.core.workflow import WorkflowSpec

    if not approval.reason:
        return None
    saved = runs.get_state(approval.run_id).get("spec") if approval.run_id else None
    return held_detail(approval.reason, approval.run_id,
                       WorkflowSpec.model_validate(saved) if saved else None)


def resolve(approval_id: int, *, approver: str, decision: str,
            rationale: str | None = None, conditions: list[dict] | None = None,
            adopt: list[str] | None = None) -> dict:
    """Approve or reject. decision ∈ {approve, reject}. Records approval latency as a KPI and the
    decision record. A reason is required to reject, and to approve a decision a reviewer
    challenged (an override).

    Approving puts the decision's obligations in force as commitments (roadmap 9): a
    conditional gate's conditions, the `conditions` the approver attaches ({text, due, debtor})
    and the alternatives they `adopt` (message ids of ALTERNATIVE verdicts on this decision)."""
    if decision not in {"approve", "reject"}:
        raise ValueError("decision must be approve|reject")
    rationale = (rationale or "").strip() or None
    with get_session() as s:
        approval = s.get(Approval, approval_id)
        if approval is None:
            raise KeyError(f"approval {approval_id} not found")
        if approval.decision != "pending":
            raise ValueError(f"already resolved: {approval.decision}")
        if decision == "reject" and (conditions or adopt):
            raise ValueError("conditions and adopted alternatives come with an approval only")
        if any(not (c.get("text") or "").strip() for c in conditions or []):
            raise ValueError("every condition needs a text")
        commitments.adoptable(approval.message_id, adopt)
        target = s.get(AgentMessageRow, approval.message_id)
        if target is not None:  # once someone is Accountable, only they decide (roadmap 9)
            kind, subject, _ = decisions.describe((target.payload or {}).get("schema"),
                                                  (target.payload or {}).get("data") or {},
                                                  target.task_ref)
            roles.check_accountable(kind, decisions._project_of(kind, subject), approver)
        challenged = bool((approval.reason or {}).get("challenges"))
        if rationale is None and (decision == "reject" or challenged):
            raise ValueError("a reason is required to reject, or to approve a decision a "
                             "reviewer challenged")

        msg = s.get(AgentMessageRow, approval.message_id)
        now = datetime.now(UTC)
        approval.decision = decision
        approval.approver = approver
        approval.decided_at = now
        approval.rationale = rationale

        if msg is not None:
            requested = msg.timestamp
            if requested.tzinfo is None:
                requested = requested.replace(tzinfo=UTC)
            latency = (now - requested).total_seconds()
            kpi.record_approval_latency(latency, message_id=approval.message_id)

        run_id, message_id = approval.run_id, approval.message_id
        result = {
            "approval_id": approval_id,
            "message_id": approval.message_id,
            "decision": decision,
            "approver": approver,
            "rationale": rationale,
            "run_id": run_id,
        }
        payload = (msg.payload or {}) if msg is not None else {}
        described = decisions.describe(payload.get("schema"), payload.get("data") or {},
                                       msg.task_ref if msg is not None else "")
        sender, evidence = (msg.sender, msg.evidence) if msg is not None else ("?", None)
    record = decisions.decided_by_person(
        message_id, kind=described[0], subject=described[1], title=described[2],
        approver=approver, decision=decision, rationale=rationale, approval_id=approval_id,
        run_id=run_id, agent=sender, evidence=evidence)
    result["decision_record"] = record["id"]
    if decision == "approve":
        owed = commitments.from_gate(message_id, creditor=approver, by=approver,
                                     decision_id=record["id"], approval_id=approval_id)
        owed += commitments.from_approval(message_id, approver=approver, approval_id=approval_id,
                                          decision_id=record["id"], conditions=conditions,
                                          adopt=adopt)
        result["commitments"] = [c["id"] for c in owed]
    project = decisions._project_of(described[0], described[1])
    informed = roles.who(described[0], "I", project)
    emit_later([approval_resolved_event(result, {"recipients": {"inform": informed}}
                                        if informed else None)])
    run_status = _continue_run(run_id, decision, approver)
    return {**result, "run_status": run_status} if run_status else result


def _continue_run(run_id: str | None, decision: str, approver: str) -> str | None:
    """A run paused at this gate ends on a rejection and resumes once nothing is pending.

    The decision is already recorded, so a failing agent marks the run failed, not the request.
    """
    from ma_pmo.core.executor import resume_run

    run = runs.get_run(run_id) if run_id else None
    if run is None or run["status"] != runs.WAITING:
        return None
    if decision == "reject":
        runs.cancel(run["run_id"], f"approval rejected by {approver}")
    elif not runs.pending_approvals(run["run_id"]):
        try:
            return resume_run(run["run_id"])["status"]
        except Exception as e:
            _log.warning("run_resume_failed", run_id=run["run_id"], error=str(e)[:200])
    return (runs.get_run(run["run_id"]) or {}).get("status")
