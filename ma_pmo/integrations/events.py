"""Turn agent messages and approval decisions into integration `Event`s."""
from __future__ import annotations

from typing import Any

from ma_pmo.core.config import get_settings
from ma_pmo.core.i18n import tr
from ma_pmo.core.schemas.message import AgentMessage
from ma_pmo.integrations.base import Event, EventType


def _link(path: str) -> str:
    return get_settings().public_url.rstrip("/") + path


def events_from_message(message: AgentMessage, gated: bool) -> list[Event]:
    """Events worth notifying about for one published message (may be empty)."""
    schema = message.payload.schema_
    data: dict[str, Any] = message.payload.data
    ref = message.task_ref
    edata: dict[str, Any] = {"message_id": message.message_id, **data}
    events: list[Event] = []

    if schema == "risk_alert.v1" and data.get("severity") in ("high", "critical"):
        events.append(
            Event(
                type=EventType.RISK_DETECTED,
                title=tr(
                    f"{data.get('severity', '').upper()} risk on {data.get('project_id')}",
                    f"{data.get('project_id')} {data.get('severity', '').upper()} 리스크 탐지",
                ),
                summary=f"{data.get('signal', '')}\n→ {data.get('mitigation', '')}",
                severity="critical",
                url=_link("/"),
                task_ref=ref,
                data=edata,
            )
        )
    elif schema == "gate_review.v1" and data.get("decision") == "fail":
        conditions = "; ".join(data.get("conditions") or [])
        events.append(
            Event(
                type=EventType.GATE_FAILED,
                title=tr(
                    f"Gate {data.get('gate')} failed for {data.get('project_id')}",
                    f"{data.get('project_id')} 게이트 {data.get('gate')} 미통과",
                ),
                summary=conditions or tr("Critical criteria not met.", "필수 기준 미충족"),
                severity="warning",
                url=_link("/"),
                task_ref=ref,
                data=edata,
            )
        )
    elif schema == "report.v1":
        events.append(
            Event(
                type=EventType.REPORT_GENERATED,
                title=tr(
                    f"Executive report ready · {data.get('scope', '')}",
                    f"경영 보고서 생성 · {data.get('scope', '')}",
                ),
                summary=str(data.get("executive_summary", ""))[:500],
                severity="info",
                url=_link("/"),
                task_ref=ref,
                data=edata,
            )
        )

    if gated:
        events.append(
            Event(
                type=EventType.APPROVAL_REQUESTED,
                title=tr(
                    f"Approval needed: {schema} from {message.sender}",
                    f"승인 필요: {message.sender}의 {schema}",
                ),
                summary=tr(
                    f"confidence {message.confidence} · {message.task_ref}",
                    f"신뢰도 {message.confidence} · {message.task_ref}",
                ),
                severity="warning",
                url=_link("/approvals"),
                task_ref=ref,
                data=edata,
            )
        )
    return events


def approval_resolved_event(result: dict) -> Event:
    approved = result.get("decision") == "approve"
    return Event(
        type=EventType.APPROVAL_RESOLVED,
        title=tr(
            f"Approval #{result.get('approval_id')} {'approved' if approved else 'rejected'}",
            f"승인 #{result.get('approval_id')} {'승인됨' if approved else '반려됨'}",
        ),
        summary=tr(f"by {result.get('approver')}", f"처리자 {result.get('approver')}"),
        severity="info",
        url=_link("/approvals"),
        data=dict(result),
    )


def make_test_event() -> Event:
    return Event(
        type=EventType.TEST,
        title=tr("MA-PMO test notification", "MA-PMO 테스트 알림"),
        summary=tr(
            "If you can read this, the integration works. 🎉",
            "이 메시지가 보이면 연동이 정상입니다. 🎉",
        ),
        url=_link("/"),
    )
