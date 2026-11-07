"""What the dashboard's switcher reads: the caller's workspaces and the portfolios in one."""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import delete

from ma_pmo.api.auth import ApiKeyAuthenticator, AuthMiddleware
from ma_pmo.api.main import app as default_app
from ma_pmo.api.main import language
from ma_pmo.api.routers import risks
from ma_pmo.api.routers import workspaces as workspaces_router
from ma_pmo.core import workspace
from ma_pmo.db import workspaces
from ma_pmo.db.models import Membership, Portfolio, Project, Risk, Workspace
from ma_pmo.db.session import get_session

ACME = "acme-list"
ROOT = "root-listing-key-0123456789"
VIC = "vic-listing-key-0123456789"
BOB = "bob-listing-key-0123456789"
NOBODY = "nobody-listing-key-0123456789"
KEYS = (f"root:admin:{ROOT},vic:{ACME}/viewer:{VIC},bob:{ACME}/viewer:{BOB},"
        f"nobody:{ACME}/viewer:{NOBODY}")


def _client() -> TestClient:
    app = FastAPI()
    app.add_middleware(AuthMiddleware, authenticator=ApiKeyAuthenticator.parse(KEYS))
    app.middleware("http")(language)
    app.include_router(workspaces_router.router)
    app.include_router(risks.router)
    return TestClient(app)


@pytest.fixture
def acme():
    workspaces.create(ACME, "Acme")
    with workspace.use(ACME), get_session() as s:
        s.add(Portfolio(id="PF-A", name="Acme A", period="2026-Q4", plan_start="2026-W40"))
        s.add(Portfolio(id="PF-B", name="Acme B", period="2026-Q4"))
    yield ACME
    with workspace.use(ACME), get_session() as s:
        for model in (Risk, Project, Portfolio):
            s.execute(delete(model))
    with get_session() as s:
        s.execute(delete(Membership).where(Membership.workspace_id == ACME))
        s.execute(delete(Workspace).where(Workspace.id == ACME))


def _ids(response) -> list[str]:
    assert response.status_code == 200
    return [w["id"] for w in response.json()["workspaces"]]


def test_a_caller_sees_only_the_workspaces_they_can_enter(acme):
    client = _client()
    everywhere = [w["id"] for w in workspaces.list_all()]
    assert _ids(client.get("/workspaces", headers={"X-API-Key": ROOT})) == everywhere
    assert {"default", ACME} <= set(everywhere)
    # a key granted only in acme lists acme, and needs no X-Workspace to ask
    mine = client.get("/workspaces", headers={"X-API-Key": VIC}).json()
    assert mine["workspaces"] == [{"id": ACME, "name": "Acme", "roles": ["viewer"]}]
    assert mine["default"] == "default"


def test_database_memberships_add_workspaces_and_roles(acme):
    workspaces.grant("default", "bob", "operator")
    workspaces.grant(ACME, "bob", "approver")
    try:
        listed = _client().get("/workspaces", headers={"X-API-Key": BOB}).json()["workspaces"]
        assert {w["id"]: w["roles"] for w in listed} == {
            "default": ["operator"], ACME: ["approver", "viewer"]}
    finally:
        workspaces.revoke("default", "bob", "operator")


def test_listing_still_needs_credentials(acme):
    assert _client().get("/workspaces").status_code == 401
    assert _client().get("/workspaces", headers={"X-API-Key": "x" * 20}).status_code == 401


def test_a_workspace_the_caller_cannot_enter_is_not_listed(acme):
    with get_session() as s:
        s.add(Workspace(id="secret-ws", name="Secret"))
    try:
        assert "secret-ws" not in _ids(_client().get("/workspaces",
                                                     headers={"X-API-Key": NOBODY}))
        assert "secret-ws" in _ids(_client().get("/workspaces", headers={"X-API-Key": ROOT}))
    finally:
        with get_session() as s:
            s.execute(delete(Workspace).where(Workspace.id == "secret-ws"))


def test_auth_off_lists_every_workspace(acme):
    listed = TestClient(default_app).get("/workspaces").json()["workspaces"]
    assert {w["id"] for w in listed} >= {"default", ACME}
    assert all(w["roles"] == ["admin", "approver", "operator", "viewer"] for w in listed)


def test_portfolios_are_those_of_the_requested_workspace(acme):
    client = TestClient(default_app)
    there = client.get("/portfolios", headers={workspace.HEADER: ACME}).json()
    assert [p["id"] for p in there["portfolios"]] == ["PF-A", "PF-B"]
    assert there["portfolios"][0] == {"id": "PF-A", "name": "Acme A", "period": "2026-Q4",
                                      "plan_start": "2026-W40"}
    here = {p["id"] for p in client.get("/portfolios").json()["portfolios"]}
    assert here and not here & {"PF-A", "PF-B"}
    assert client.get("/portfolios", headers={workspace.HEADER: "nope"}).status_code == 404


def test_risks_can_be_limited_to_one_portfolio(acme):
    with workspace.use(ACME), get_session() as s:
        for pf in ("PF-A", "PF-B"):
            s.add(Project(id=f"P-{pf}", portfolio_id=pf))
        s.flush()
        for pf in ("PF-A", "PF-B"):
            s.add(Risk(id=f"R-{pf}", project_id=f"P-{pf}", signal="late", severity="high"))
    client = TestClient(default_app)
    headers = {workspace.HEADER: ACME}
    every = {r["id"] for r in client.get("/risks", headers=headers).json()}
    only_a = [r["id"] for r in client.get("/risks", params={"scope": "PF-A"},
                                          headers=headers).json()]
    assert every == {"R-PF-A", "R-PF-B"} and only_a == ["R-PF-A"]
