"""One SPI for agents and reports: earned over planned value at the as-of date (`agents/evm.py`)."""
from __future__ import annotations

from datetime import date

from ma_pmo.agents import common, evm
from ma_pmo.agents.gates import evaluate_gate
from ma_pmo.core.config import get_settings

HALF = {"project_id": "P", "status": "green", "percent_complete": 50.0,
        "planned_start": "2026-01-01", "planned_finish": "2026-03-02", "deadline": "2026-03-31",
        "tasks": [{"task_id": "T1", "wbs": "1", "effort": 100.0, "deps": [],
                   "percent_complete": 50.0}]}


def test_spi_is_earned_over_planned_value_at_the_as_of_date():
    assert evm.spi(HALF, date(2026, 1, 31)) == 1.0  # half done, half the plan elapsed
    assert evm.spi(HALF, date(2026, 1, 16)) == 2.0  # ahead
    assert evm.spi(HALF, date(2026, 6, 1)) == 0.5  # past the plan: the completed share
    assert evm.spi(HALF, date(2025, 12, 1)) is None  # before the planned start
    assert evm.forecast(HALF, 0.5) == "2026-05-01" and evm.forecast(HALF, None) == "2026-03-02"


def test_agents_use_the_same_spi(monkeypatch):
    monkeypatch.setattr(get_settings(), "report_as_of", "2026-01-31")
    assert common.spi(HALF) == 1.0
    _, checklist, _ = evaluate_gate(HALF, "G3-execution")
    spi_check = next(c for c in checklist if c.name == "SPI ≥ 0.8")
    assert spi_check.passed  # 0.5 done halfway through the plan is on schedule
    monkeypatch.setattr(get_settings(), "report_as_of", "2026-06-01")
    _, checklist, _ = evaluate_gate(HALF, "G3-execution")
    assert not next(c for c in checklist if c.name == "SPI ≥ 0.8").passed
