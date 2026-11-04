"""API authentication: off by default, API keys with roles, custom authenticators.

The shared `app` runs with auth off (the default), so the role checks are exercised on a
second app built from the same routers with an API-key authenticator.
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ma_pmo.api.auth import (
    ApiKeyAuthenticator,
    AuthConfigError,
    AuthMiddleware,
    Principal,
    build_authenticator,
    required_role,
)
from ma_pmo.api.main import app as default_app
from ma_pmo.api.main import language, whoami
from ma_pmo.api.routers import approvals, integrations
from ma_pmo.core.config import Settings

VIEWER = "viewer-key-0123456789"
APPROVER = "approver-key-0123456789"
ADMIN = "admin-key-0123456789abc"
KEYS = f"vic:viewer:{VIEWER},alice:approver:{APPROVER},root:admin:{ADMIN}"


def _secured_app() -> TestClient:
    app = FastAPI()
    # same order as the real app: auth inside the language middleware
    app.add_middleware(AuthMiddleware, authenticator=ApiKeyAuthenticator.parse(KEYS))
    app.middleware("http")(language)
    app.include_router(approvals.router)
    app.include_router(integrations.router)
    app.get("/health")(lambda: {"status": "ok"})
    app.get("/auth/whoami")(whoami)
    return TestClient(app)


def _pending_id(client: TestClient, key: str) -> int:
    default = TestClient(default_app)
    default.post("/demo/gated-message")
    return client.get("/approvals", headers={"X-API-Key": key}).json()[0]["approval_id"]


@pytest.mark.smoke
def test_off_by_default_keeps_the_demo_open():
    client = TestClient(default_app)
    assert client.get("/approvals").status_code == 200
    me = client.get("/auth/whoami").json()
    assert me["auth_enabled"] is False and "admin" in me["roles"]


@pytest.mark.smoke
def test_api_key_roles():
    client = _secured_app()
    assert client.get("/health").status_code == 200  # public
    assert client.options("/approvals").status_code != 401  # CORS preflight is never blocked

    missing = client.get("/approvals")
    assert missing.status_code == 401 and missing.headers["www-authenticate"] == "Bearer"
    wrong = {"X-API-Key": "wrong-key-0123456789"}
    assert client.get("/approvals", headers=wrong).status_code == 401

    bearer = {"Authorization": f"Bearer {VIEWER}"}
    assert client.get("/approvals", headers=bearer).status_code == 200
    approval_id = _pending_id(client, VIEWER)
    body = {"decision": "approve"}
    denied = client.post(f"/approvals/{approval_id}", json=body, headers={"X-API-Key": VIEWER})
    assert denied.status_code == 403
    assert client.post("/integrations/slack/test",
                       headers={"X-API-Key": APPROVER}).status_code == 403
    me = client.get("/auth/whoami", headers={"X-API-Key": ADMIN}).json()
    assert me == {"subject": "root", "roles": ["admin"], "auth_enabled": True}


def test_approver_is_the_authenticated_user():
    client = _secured_app()
    approval_id = _pending_id(client, APPROVER)
    resp = client.post(f"/approvals/{approval_id}",
                       json={"approver": "someone-else", "decision": "approve"},
                       headers={"X-API-Key": APPROVER})
    assert resp.status_code == 200, resp.text
    assert resp.json()["approver"] == "alice"


def test_error_messages_follow_the_language():
    client = _secured_app()
    assert "API 키" in client.get("/approvals?lang=ko").json()["detail"]


@pytest.mark.parametrize("spec, problem", [
    ("", "at least one"),
    ("alice:approver", "is name:role"),
    ("alice:boss:0123456789abcdef", "roles must be"),
    ("alice:viewer:short", "shorter than"),
    ("a:viewer:0123456789abcdef,b:admin:0123456789abcdef", "used twice"),
])
def test_bad_key_config_fails_at_startup(spec, problem):
    with pytest.raises(AuthConfigError, match=problem):
        build_authenticator(Settings(MA_PMO_AUTH_MODE="api_key", MA_PMO_API_KEYS=spec))


def test_modes():
    assert build_authenticator(Settings(MA_PMO_AUTH_MODE="off")) is None
    with pytest.raises(AuthConfigError, match="unknown"):
        build_authenticator(Settings(MA_PMO_AUTH_MODE="magic"))
    custom = build_authenticator(Settings(MA_PMO_AUTH_MODE="custom",
                                          MA_PMO_AUTHENTICATOR="tests.test_auth:header_auth"))
    assert custom is not None


class _HeaderAuth:
    """Example custom authenticator: trusts a header set by a gateway in front of the API."""

    def authenticate(self, request):
        user = request.headers.get("x-forwarded-user")
        return Principal(user, frozenset({"operator"})) if user else None


def header_auth(settings: Settings) -> _HeaderAuth:
    return _HeaderAuth()


def test_route_policy():
    assert required_role("GET", "/kpi") == "viewer"
    assert required_role("POST", "/scenarios/x/run") == "operator"
    assert required_role("POST", "/approvals/3") == "approver"
    assert required_role("POST", "/integrations/slack/test") == "admin"
    assert required_role("GET", "/docs") is None
    assert required_role("OPTIONS", "/approvals/3") is None
    assert Principal("p", frozenset({"approver"})).has("viewer")
    assert not Principal("p", frozenset({"operator"})).has("approver")
