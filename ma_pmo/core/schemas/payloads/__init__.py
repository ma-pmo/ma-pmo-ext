"""Agent output payload schemas (`.v1`).

Every agent's output is validated against its Pydantic schema (hallucination control).
"""
from pydantic import BaseModel

from ma_pmo.core.schemas.payloads.allocation_v1 import AllocationV1
from ma_pmo.core.schemas.payloads.gate_review_v1 import GateReviewV1
from ma_pmo.core.schemas.payloads.knowledge_v1 import KnowledgeV1
from ma_pmo.core.schemas.payloads.report_v1 import ReportV1
from ma_pmo.core.schemas.payloads.risk_alert_v1 import RiskAlertV1
from ma_pmo.core.schemas.payloads.routing_v1 import RoutingV1
from ma_pmo.core.schemas.payloads.schedule_v1 import ScheduleV1

# schema string -> Pydantic model registry (used for validation/deserialization)
PAYLOAD_REGISTRY: dict[str, type[BaseModel]] = {
    "report.v1": ReportV1,
    "risk_alert.v1": RiskAlertV1,
    "allocation.v1": AllocationV1,
    "schedule.v1": ScheduleV1,
    "gate_review.v1": GateReviewV1,
    "knowledge.v1": KnowledgeV1,
    "routing.v1": RoutingV1,
}

__all__ = [
    "ReportV1",
    "RiskAlertV1",
    "AllocationV1",
    "ScheduleV1",
    "GateReviewV1",
    "KnowledgeV1",
    "RoutingV1",
    "PAYLOAD_REGISTRY",
]
