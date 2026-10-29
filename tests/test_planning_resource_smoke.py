"""A2/A3 end-to-end smoke tests — deterministic, so no LLM mocking needed.

Runs A2 (CPM) and A3 (allocation) on the fixture portfolio and checks KPIs and persistence.
"""
from __future__ import annotations

from sqlalchemy import select

from ma_pmo.agents.planning import PlanningAgent
from ma_pmo.agents.resource import ResourceAgent
from ma_pmo.db.models import Allocation, KpiEvent
from ma_pmo.db.session import get_session


def test_a2_planning_records_delivery_kpi():
    result = PlanningAgent().run({"task_ref": "PORTFOLIO#2026-Q1"})
    assert result["outputs"], "expected schedule outputs"
    assert all(o["schema"] == "schedule.v1" for o in result["outputs"])
    # a critical path is computed
    assert any(o["data"]["critical_path"] for o in result["outputs"])

    with get_session() as s:
        spi = s.scalars(select(KpiEvent).where(KpiEvent.metric == "spi")).all()
        assert spi, "SPI delivery KPI recorded"


def test_a3_resource_allocates_and_records_utilization():
    result = ResourceAgent().run({"task_ref": "PORTFOLIO#2026-Q1"})
    data = result["outputs"][0]["data"]
    assert data["plan"], "expected an allocation plan"
    assert data["utilization_pct"] is not None

    with get_session() as s:
        allocs = s.scalars(select(Allocation)).all()
        assert allocs, "Allocation persisted"
        util = s.scalars(
            select(KpiEvent).where(KpiEvent.metric == "utilization_pct")
        ).all()
        idle = s.scalars(select(KpiEvent).where(KpiEvent.metric == "idle_pct")).all()
        assert util and idle, "utilization/idle resource KPIs recorded (H2)"
