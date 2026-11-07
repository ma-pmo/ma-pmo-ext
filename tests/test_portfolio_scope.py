"""Portfolios do not touch each other's plans, and weeks come from the portfolio or the clock."""
from __future__ import annotations

import ast
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete, select, text

import ma_pmo
from ma_pmo.agents.allocation import allocate
from ma_pmo.agents.resource import ResourceAgent
from ma_pmo.api.main import app
from ma_pmo.core.scope import DEFAULT_SCOPE
from ma_pmo.db import migrate
from ma_pmo.db.models import Allocation, Portfolio, Project, Resource, Task
from ma_pmo.db.session import get_session
from ma_pmo.eval.dataset import load_dataset

OTHER = "PORTFOLIO#OTHER"


def _agent() -> ResourceAgent:
    agent = ResourceAgent(calendar=None)
    agent.calendar = None  # ignore any MA_PMO_CALENDAR_DIR on the machine running the tests
    return agent


def _plans() -> dict[str, list[tuple]]:
    with get_session() as s:
        rows = s.execute(
            select(Project.portfolio_id, Allocation.project_id, Allocation.resource_id,
                   Allocation.week, Allocation.hours)
            .join(Project, Project.id == Allocation.project_id)
            .order_by(Allocation.id)
        ).all()
    plans: dict[str, list[tuple]] = {}
    for portfolio, *line in rows:
        plans.setdefault(portfolio, []).append(tuple(line))
    return plans


@pytest.fixture
def other_portfolio():
    """A second portfolio competing for the sample's R-01, with hours left to place."""
    with get_session() as s:
        s.merge(Portfolio(id=OTHER, name="Other", period="2026-Q1", plan_start="2026-W03"))
        s.flush()
        s.merge(Project(id="OTHER-1", portfolio_id=OTHER, skill="backend"))
        s.flush()
        s.merge(Task(id="OTHER-1-T", project_id="OTHER-1", effort=30.0))
    yield
    with get_session() as s:
        s.execute(delete(Allocation).where(Allocation.project_id == "OTHER-1"))
        s.execute(delete(Task).where(Task.project_id == "OTHER-1"))
        s.execute(delete(Project).where(Project.id == "OTHER-1"))
        s.execute(delete(Portfolio).where(Portfolio.id == OTHER))
    _agent().allocate_portfolio()


def test_allocating_one_portfolio_keeps_the_other_plan(other_portfolio):
    agent = _agent()
    agent.allocate_portfolio()
    sample = _plans()[DEFAULT_SCOPE]
    agent.allocate_portfolio(OTHER)
    assert _plans()[DEFAULT_SCOPE] == sample
    assert OTHER in _plans()


def test_rerunning_replaces_only_its_own_plan(other_portfolio):
    agent = _agent()
    agent.allocate_portfolio()
    agent.allocate_portfolio(OTHER)
    first = _plans()[OTHER]
    agent.allocate_portfolio(OTHER)
    assert _plans()[OTHER] == first  # replaced, not added to


def test_unknown_scope_erases_nothing():
    agent = _agent()
    agent.allocate_portfolio()
    before = _plans()
    assert agent.allocate_portfolio("PORTFOLIO#NOPE")["plan"] == []
    assert _plans() == before


def test_a_person_is_not_booked_twice_across_portfolios(other_portfolio):
    agent = _agent()
    agent.allocate_portfolio()
    agent.allocate_portfolio(OTHER)
    with get_session() as s:
        capacity = {r.id: r.capacity for r in s.scalars(select(Resource))}
    totals: dict[tuple[str, str], float] = {}
    for lines in _plans().values():
        for _, resource_id, week, hours in lines:
            totals[(resource_id, week)] = totals.get((resource_id, week), 0.0) + hours
    assert all(hours <= capacity[key[0]] + 0.1 for key, hours in totals.items())


def test_allocations_can_be_listed_per_portfolio(other_portfolio):
    agent = _agent()
    agent.allocate_portfolio()
    agent.allocate_portfolio(OTHER)
    lines = TestClient(app).get("/allocations", params={"scope": OTHER}).json()
    assert lines and {ln["project_id"] for ln in lines} == {"OTHER-1"}


PROJECT = [{"project_id": "P", "skill": "data", "tasks": [{"effort": 80.0}]}]
PERSON = [{"id": "R", "skill": "data", "capacity": 40.0}]


def test_weeks_cross_into_the_next_iso_year():
    weeks = [ln.week for ln in allocate(PROJECT, PERSON, start="2026-W53").lines]
    assert weeks == ["2026-W53", "2027-W01"]


def test_without_a_start_allocation_begins_this_week():
    year, week, _ = date.today().isocalendar()
    assert allocate(PROJECT, PERSON).lines[0].week == f"{year}-W{week:02d}"


def test_sample_portfolio_keeps_its_own_start():
    plan = _agent().allocate_portfolio()["plan"]
    assert min(ln["week"] for ln in plan) == "2026-W03"


def test_migration_keeps_the_sample_start_and_leaves_others_open(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'm.db'}")
    migrate.upgrade(engine, "0003_resume")
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO portfolio (id, name, period) VALUES "
                          "('PORTFOLIO#2026-Q1', 'Sample', 'Q1'), ('P', 'Mine', 'Q1')"))
    migrate.upgrade(engine)
    with engine.connect() as conn:
        rows = dict(conn.execute(text("SELECT id, plan_start FROM portfolio")).all())
    assert rows == {"PORTFOLIO#2026-Q1": "2026-W03", "P": None}


@pytest.mark.parametrize("value, ok", [("2027-W03", True), ("2027-W99", False), ("soon", False)])
def test_dataset_checks_plan_start(tmp_path, value, ok):
    (tmp_path / "portfolio.csv").write_text(
        f"id,name,period,plan_start\nPORTFOLIO#X,X,2027-Q1,{value}\n", encoding="utf-8")
    _, issues = load_dataset(tmp_path)
    assert ok != any("plan_start" in i.message for i in issues)


def test_the_default_portfolio_is_named_in_one_place():
    root = Path(ma_pmo.__file__).parent
    found = []
    for path in root.rglob("*.py"):
        if "learn" in path.parts or path.name == "config.py":  # labs are standalone
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Constant) and node.value == "PORTFOLIO#2026-Q1":
                found.append(f"{path.relative_to(root)}:{node.lineno}")
    assert found == []
