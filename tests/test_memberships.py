"""Roles per workspace: key grants, database memberships, and strangers who see nothing."""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import delete

from ma_pmo.api.auth import ApiKeyAuthenticator, AuthMiddleware, Principal
from ma_pmo.api.main import app as default_app
from ma_pmo.api.main import language, whoami
from ma_pmo.api.routers import approvals, runs
from ma_pmo.cli import main as cli
from ma_pmo.core import workspace
from ma_pmo.db import workspaces
from ma_pmo.db.models import AgentMessageRow, Approval, KpiEvent, Membership, Workspace
from ma_pmo.db.session import get_session

ACME = "acme"
GLOBAL = "global-admin-key-0123456789"
ACME_VIEWER = "acme-viewer-key-0123456789"
BOB = "bob-identity-key-0123456789"
KEYS = (f"root:admin:{GLOBAL},vic:{ACME}/viewer:{ACME_VIEWER},"
        f"bob:{ACME}/viewer:{BOB}")


def _client() -> TestClient:
    app = FastAPI()
    app.add_middleware(AuthMiddleware, authenticator=ApiKeyAuthenticator.parse(KEYS))
    app.middleware("http")(language)
    app.include_router(approvals.router)
    app.include_router(runs.router)
    app.get("/auth/whoami")(whoami)
    return TestClient(app)


def _as(key: str, where: str | None = None) -> dict:
    headers = {"X-API-Key": key}
    if where:
        headers[workspace.HEADER] = where
    return headers


@pytest.fixture
def acme():
    workspaces.create(ACME, "Acme")
    yield ACME
    with workspace.use(ACME), get_session() as s:  # approving also records a KPI
        for model in (Approval, KpiEvent, AgentMessageRow):
            s.execute(delete(model))
    with get_session() as s:
        s.execute(delete(Membership).where(Membership.workspace_id == ACME))
        s.execute(delete(Workspace).where(Workspace.id == ACME))


def _pending_in(where: str) -> int:
    TestClient(default_app).post("/demo/gated-message", headers={workspace.HEADER: where})
    with workspace.use(where):
        from ma_pmo.core import hitl

        return hitl.list_pending()[0]["approval_id"]


def test_key_grants_parse_into_workspaces():
    auth = ApiKeyAuthenticator.parse(f"vic:viewer+{ACME}/approver+{ACME}/operator:{ACME_VIEWER}")
    (principal,) = auth._keys.values()
    assert principal.roles == {"viewer"}
    assert principal.memberships == {ACME: {"approver", "operator"}}
    assert principal.in_workspace(ACME).roles == {"viewer", "approver", "operator"}
    assert principal.in_workspace("default").roles == {"viewer"}


def test_no_roles_means_no_access_not_read_access():
    assert not Principal("nobody").has("viewer")
    assert Principal("reader", frozenset({"approver"})).has("viewer")


def test_a_workspace_key_works_only_there(acme):
    client = _client()
    assert client.get("/runs", headers=_as(ACME_VIEWER, ACME)).status_code == 200
    # elsewhere it looks exactly like a workspace that does not exist
    elsewhere = client.get("/runs", headers=_as(ACME_VIEWER))
    unknown = client.get("/runs", headers=_as(GLOBAL, "nope"))
    assert elsewhere.status_code == unknown.status_code == 404
    assert "default" in elsewhere.json()["detail"]


def test_roles_everywhere_still_work_in_every_workspace(acme):
    client = _client()
    for where in ("default", ACME):
        me = client.get("/auth/whoami", headers=_as(GLOBAL, where)).json()
        assert me["workspace"] == where and me["roles"] == ["admin"]


def test_a_membership_in_the_database_adds_a_role_there_only(acme):
    client = _client()
    acme_approval = _pending_in(ACME)
    default_approval = _pending_in("default")
    body = {"decision": "approve"}
    assert client.post(f"/approvals/{acme_approval}", json=body,
                       headers=_as(BOB, ACME)).status_code == 403  # viewer only

    assert workspaces.grant(ACME, "bob", "approver") is True
    assert workspaces.grant(ACME, "bob", "approver") is False  # already
    approved = client.post(f"/approvals/{acme_approval}", json=body, headers=_as(BOB, ACME))
    assert approved.status_code == 200 and approved.json()["approver"] == "bob"
    # an approver in acme is a stranger in default
    assert client.post(f"/approvals/{default_approval}", json=body,
                       headers=_as(BOB)).status_code == 404

    assert workspaces.revoke(ACME, "bob", "approver") is True
    assert client.get("/auth/whoami", headers=_as(BOB, ACME)).json()["roles"] == ["viewer"]


def test_auth_off_keeps_every_workspace_open(acme):
    client = TestClient(default_app)
    me = client.get("/auth/whoami", headers={workspace.HEADER: ACME}).json()
    assert me["auth_enabled"] is False and me["workspace"] == ACME


def test_grants_are_checked():
    with pytest.raises(ValueError, match="role must be"):
        workspaces.grant("default", "x", "boss")
    with pytest.raises(ValueError, match="unknown workspace"):
        workspaces.grant("nope", "x", "viewer")
    with pytest.raises(ValueError, match="exists"):
        workspaces.create("default")
    with pytest.raises(ValueError, match="without spaces"):
        workspaces.create("two words")


def test_cli_manages_workspaces(capsys):
    try:
        assert cli(["workspace", "create", "cli-ws", "--name", "From CLI"]) == 0
        assert cli(["workspace", "grant", "cli-ws", "carol", "operator"]) == 0
        assert cli(["workspace", "members", "cli-ws"]) == 0
        assert cli(["workspace", "list"]) == 0
        out = capsys.readouterr().out
        assert "carol" in out and "operator" in out and "From CLI" in out
        assert cli(["workspace", "grant", "cli-ws", "carol", "boss"]) == 1
        assert cli(["workspace", "revoke", "cli-ws", "carol", "operator"]) == 0
        assert cli(["workspace", "revoke", "cli-ws", "carol", "operator"]) == 1
    finally:
        with get_session() as s:
            s.execute(delete(Membership).where(Membership.workspace_id == "cli-ws"))
            s.execute(delete(Workspace).where(Workspace.id == "cli-ws"))
