"""Human-in-the-loop approval gate — paper §8 governance.

High-risk decisions (budget, scope, contracts, external communication) are final only
after passing a human approval gate.
- LangGraph `interrupt` pauses the graph (approval node)
- the approval queue (approval table) lists and resolves pending items
- approval latency is measured as a KPI (cost axis)
"""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select

from ma_pmo.core import kpi, runs
from ma_pmo.core.obs import get_logger
from ma_pmo.db.models import AgentMessageRow, Approval
from ma_pmo.db.session import get_session
from ma_pmo.integrations.dispatch import emit
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
            }
            for a, m in rows
        ]


def _review(approval: Approval) -> dict | None:
    from ma_pmo.core.commit import held_detail
    from ma_pmo.core.workflow import WorkflowSpec

    if not approval.reason:
        return None
    saved = runs.get_state(approval.run_id).get("spec") if approval.run_id else None
    return held_detail(approval.reason, approval.run_id,
                       WorkflowSpec.model_validate(saved) if saved else None)


def resolve(approval_id: int, *, approver: str, decision: str) -> dict:
    """Approve or reject. decision ∈ {approve, reject}. Records approval latency as a KPI."""
    if decision not in {"approve", "reject"}:
        raise ValueError("decision must be approve|reject")
    with get_session() as s:
        approval = s.get(Approval, approval_id)
        if approval is None:
            raise KeyError(f"approval {approval_id} not found")
        if approval.decision != "pending":
            raise ValueError(f"already resolved: {approval.decision}")

        msg = s.get(AgentMessageRow, approval.message_id)
        now = datetime.now(UTC)
        approval.decision = decision
        approval.approver = approver
        approval.decided_at = now

        if msg is not None:
            requested = msg.timestamp
            if requested.tzinfo is None:
                requested = requested.replace(tzinfo=UTC)
            latency = (now - requested).total_seconds()
            kpi.record_approval_latency(latency, message_id=approval.message_id)

        run_id = approval.run_id
        result = {
            "approval_id": approval_id,
            "message_id": approval.message_id,
            "decision": decision,
            "approver": approver,
        }
    emit([approval_resolved_event(result)])
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
