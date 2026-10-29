"""Five-axis KPI telemetry — paper §7.

Axes: time · resource · delivery · risk · cost
Every agent action and all LLM usage are recorded as kpi_event rows, leaving the
empirical evidence for hypotheses H1–H5.
"""
from __future__ import annotations

from enum import Enum

from ma_pmo.core.obs import get_logger
from ma_pmo.db.models import KpiEvent
from ma_pmo.db.session import get_session

_log = get_logger("kpi")


class Axis(str, Enum):
    TIME = "time"
    RESOURCE = "resource"
    DELIVERY = "delivery"
    RISK = "risk"
    COST = "cost"


def record(
    axis: Axis | str,
    metric: str,
    value: float,
    *,
    project_id: str | None = None,
    meta: dict | None = None,
) -> None:
    """Record a single KPI event."""
    axis_val = axis.value if isinstance(axis, Axis) else axis
    with get_session() as s:
        s.add(
            KpiEvent(
                axis=axis_val,
                metric=metric,
                value=float(value),
                project_id=project_id,
                meta=meta or {},
            )
        )
    _log.info("kpi", axis=axis_val, metric=metric, value=float(value), project_id=project_id)


# ─── convenience helpers (frequently used metrics) ──────────────


def record_report_cycle_time(seconds: float, *, scope: str | None = None) -> None:
    """RCT: seconds from report request to completion. Paper H1."""
    record(Axis.TIME, "report_cycle_time_sec", seconds, meta={"scope": scope})


def record_llm_cost(
    *, model: str, prompt_tokens: int, completion_tokens: int, latency_ms: float, agent: str
) -> None:
    """Agent operating cost (tokens, latency) — the cost axis the original simulation omitted."""
    record(
        Axis.COST,
        "llm_tokens_total",
        prompt_tokens + completion_tokens,
        meta={
            "model": model,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "latency_ms": latency_ms,
            "agent": agent,
        },
    )


def record_approval_latency(seconds: float, *, message_id: str) -> None:
    """Approval latency — HITL switching cost (cost axis)."""
    record(Axis.COST, "approval_latency_sec", seconds, meta={"message_id": message_id})
