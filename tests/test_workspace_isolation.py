"""Nothing crosses workspaces: every table, every GET route, ids from elsewhere, and new runs.

A second workspace gets one marked row in every table plus the sample data. From `default`,
no query and no GET response may show a marked row. A new table or GET route fails here until
it is covered: add a row to `_marked_rows` or the route to the tables below.
"""
from __future__ import annotations

import re
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select

from ma_pmo.api.main import app
from ma_pmo.core import workspace
from ma_pmo.db.init import load_fixtures, load_lessons
from ma_pmo.db.models import (
    AgentMessageRow,
    Allocation,
    Approval,
    Base,
    KnowledgeDoc,
    KpiEvent,
    Portfolio,
    Project,
    Report,
    Resource,
    Risk,
    Run,
    RunStep,
    Scoped,
    Task,
    WorkflowVersion,
    Workspace,
)
from ma_pmo.db.session import get_session

OTHER = "isolated"
MARK = "zzleak"
EVERY = {workspace.ALL_WORKSPACES: True}

# required query parameters of GET routes
QUERY = {"/knowledge/search": {"q": "lesson risk schedule"}}
# GET routes with path parameters: the other workspace's id, and what `default` must answer
PATH = {
    "/runs/{run_id}": (f"/runs/run-{MARK}", lambda r: r.status_code == 404),
    "/portfolio/{portfolio_id}": (f"/portfolio/PORTFOLIO%23{MARK}",
                                  lambda r: r.json()["found"] is False),
    # workflows are shared by every workspace; none carries workspace data
    "/workflows/{workflow_id}": (f"/workflows/{MARK}", lambda r: r.status_code == 404),
    "/runs/{run_id}/workflow": (f"/runs/run-{MARK}/workflow", lambda r: r.status_code == 404),
    # another workspace's version 9 of a shared workflow
    "/workflows/{workflow_id}/versions": (
        "/workflows/weekly_status/versions",
        lambda r: r.status_code == 200 and MARK not in r.text
        and 9 not in {v["version"] for v in r.json()["versions"]}),
    "/workflows/{workflow_id}/versions/{version}": ("/workflows/weekly_status/versions/9",
                                                    lambda r: r.status_code == 404),
}


def _marked_rows() -> list[Base]:
    now = datetime.now(UTC)
    return [
        Portfolio(id=f"PORTFOLIO#{MARK}", name=MARK, period=MARK),
        Project(id=f"{MARK}-P", portfolio_id=f"PORTFOLIO#{MARK}", skill="backend",
                status="red"),
        Task(id=f"{MARK}-T", project_id=f"{MARK}-P", wbs=MARK, effort=10.0),
        Resource(id=f"{MARK}-R", skill="backend"),
        Allocation(project_id=f"{MARK}-P", resource_id=f"{MARK}-R", week="2026-W03", hours=1.0),
        Risk(id=f"RISK-{MARK}", project_id=f"{MARK}-P", signal=MARK, severity="high",
             detected_at=now, mitigation=MARK),
        Report(id=f"RPT-{MARK}", scope=MARK, content={"note": MARK}),
        Run(id=f"run-{MARK}", kind="scenario", workflow=MARK, scope=MARK,
            status="waiting_approval"),
        RunStep(run_id=f"run-{MARK}", seq=1, agent="A4", status="succeeded"),
        AgentMessageRow(message_id=f"msg-{MARK}", sender="A4", receiver="A1", intent="propose",
                        task_ref=MARK, payload={"note": MARK}, human_gate_required=True,
                        run_id=f"run-{MARK}"),
        Approval(message_id=f"msg-{MARK}", run_id=f"run-{MARK}"),
        KnowledgeDoc(id=f"{MARK}-doc", title=f"{MARK} lesson",
                     text="lesson risk schedule vendor delay", tags=[MARK]),
        KpiEvent(axis="risk", metric=MARK, value=1.0, project_id=f"{MARK}-P",
                 meta={"note": MARK}, run_id=f"run-{MARK}"),
        WorkflowVersion(workflow_id="weekly_status", version=9, status="published",
                        created_by=MARK, note=MARK,
                        spec={"id": "weekly_status", "version": 9, "category": "execution",
                              "title": {"en": MARK, "ko": MARK}, "goal": {"en": MARK, "ko": MARK},
                              "description": {"en": MARK, "ko": MARK},
                              "steps": [{"id": "A5", "agent": "A5"}]}),
    ]


def _scoped_models() -> list[type]:
    return [m.class_ for m in Base.registry.mappers if issubclass(m.class_, Scoped)]


@pytest.fixture(scope="module")
def other():
    with get_session() as s:
        s.merge(Workspace(id=OTHER, name="Isolated"))
    with workspace.use(OTHER):
        load_fixtures()
        load_lessons()
        rows = _marked_rows()
        with get_session() as s:
            for row in rows:
                s.add(row)
                s.flush()  # parents before children
            approval_id = next(r.id for r in rows if isinstance(r, Approval))
    yield {"approval_id": approval_id}
    with workspace.use(OTHER), get_session() as s:
        for model in (Approval, KpiEvent, AgentMessageRow, RunStep, Run, Risk, Allocation,
                      Task, Project, Resource, Portfolio, Report, KnowledgeDoc, WorkflowVersion):
            s.execute(delete(model))
    with get_session() as s:
        s.execute(delete(Workspace).where(Workspace.id == OTHER))


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


def test_every_table_has_a_marked_row(other):
    with workspace.use(OTHER), get_session() as s:
        empty = [m.__name__ for m in _scoped_models()
                 if not s.scalar(select(func.count()).select_from(m))]
    assert empty == []


def test_no_query_in_default_sees_another_workspace(other):
    with get_session() as s:
        seen = {m.__name__: s.scalar(select(func.count()).select_from(m)
                                     .where(m.workspace_id == OTHER))
                for m in _scoped_models()}
    assert all(n == 0 for n in seen.values()), seen


def test_joins_and_subqueries_are_filtered_too(other):
    with get_session() as s:
        joined = s.scalars(select(Task.id).join(
            Project, (Project.id == Task.project_id))).all()
        nested = s.scalars(select(Allocation.id).where(Allocation.project_id.in_(
            select(Project.id).where(Project.status == "red")))).all()
        everything = s.scalars(select(Task.id), execution_options=EVERY).all()
    assert f"{MARK}-T" not in joined and f"{MARK}-T" in everything
    with get_session() as s:
        ours = set(s.scalars(select(Allocation.id)).all())
    assert set(nested) <= ours


def _get_routes() -> dict[str, dict]:
    """Every GET route with its operation, read from the OpenAPI schema (which, unlike
    `app.routes`, also lists the routes of included routers)."""
    return {path: ops["get"] for path, ops in app.openapi()["paths"].items() if "get" in ops}


def test_no_get_route_shows_another_workspace(other, client):
    uncovered, checked = [], []
    for path, op in _get_routes().items():
        if "{" in path:
            if path not in PATH:
                uncovered.append(path)
            continue
        required = {p["name"] for p in op.get("parameters", [])
                    if p["in"] == "query" and p.get("required")}
        if required - set(QUERY.get(path, {})):
            uncovered.append(path)
            continue
        response = client.get(path, params=QUERY.get(path))
        assert response.status_code < 500, path
        assert MARK.encode() not in response.content, path
        checked.append(path)
    assert uncovered == [], "cover these routes in PATH or QUERY"
    assert {"/runs", "/risks", "/messages", "/kpi", "/allocations", "/approvals",
            "/knowledge/search"} <= set(checked)


@pytest.mark.parametrize("path", sorted(PATH))
def test_another_workspace_ids_are_not_found(other, client, path):
    url, expected = PATH[path]
    assert expected(client.get(url))


def test_another_workspace_cannot_be_changed_by_id(other, client):
    approval = client.post(f"/approvals/{other['approval_id']}", json={"decision": "approve"})
    assert approval.status_code == 404
    assert client.post(f"/runs/run-{MARK}/resume").status_code == 404
    with workspace.use(OTHER), get_session() as s:
        assert s.get(Approval, other["approval_id"]).decision == "pending"


def test_the_header_picks_the_workspace(other, client):
    mine = client.get("/runs", headers={workspace.HEADER: OTHER}).json()
    assert f"run-{MARK}" in {r["run_id"] for r in mine}
    missing = client.get("/runs", headers={workspace.HEADER: "nope"})
    assert missing.status_code == 404 and "nope" in missing.json()["detail"]


def test_a_run_writes_only_into_its_workspace(other, client):
    """knowledge_kickoff runs three steps in parallel: their threads keep the workspace."""
    response = client.post("/scenarios/knowledge_kickoff/run", headers={workspace.HEADER: OTHER})
    assert response.status_code == 200, response.text
    run_id = response.json()["run_id"]
    with get_session() as s:
        places = {(m.__name__, w) for m in (Run, RunStep, AgentMessageRow, KpiEvent, Approval)
                  for w in s.scalars(select(m.workspace_id).where(
                      (m.id if m is Run else m.run_id) == run_id), execution_options=EVERY)}
        steps = s.scalar(select(func.count()).select_from(RunStep)
                         .where(RunStep.run_id == run_id), execution_options=EVERY)
    assert steps >= 3
    assert {w for _, w in places} == {OTHER}, places
    assert {name for name, _ in places} >= {"Run", "RunStep", "AgentMessageRow"}
    assert client.get(f"/runs/{run_id}").status_code == 404
    assert client.get(f"/runs/{run_id}", headers={workspace.HEADER: OTHER}).status_code == 200


def test_the_marker_never_appears_in_route_paths():
    # a route path containing the marker would make the GET check pass by accident
    assert not any(re.search(MARK, path) for path in _get_routes())
