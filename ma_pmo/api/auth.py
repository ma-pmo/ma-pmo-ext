"""API authentication and role checks.

Off by default so the demo and the dashboard work out of the box. Turn it on with
`MA_PMO_AUTH_MODE`:

- `off`      — every request is an anonymous user with all roles (development only).
- `api_key`  — keys from `MA_PMO_API_KEYS`, sent as `Authorization: Bearer <key>` or
               `X-API-Key: <key>`. Format: `name:role+role:key`, comma-separated, e.g.
               `alice:approver:2f9c…,ci-bot:operator:8a1d…`.
- `custom`   — your own authenticator (OIDC, JWT, a gateway header, …) loaded from
               `MA_PMO_AUTHENTICATOR=package.module:factory`; `factory(settings)` returns an
               object with `authenticate(request) -> Principal | None`.

Roles: `viewer` (read), `operator` (run agents and scenarios), `approver` (resolve HITL
approvals), `admin` (everything, including integration tests). Every role can read.
"""
from __future__ import annotations

import hmac
import importlib
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Annotated, Protocol

from fastapi import Depends, Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response

from ma_pmo.core.config import Settings
from ma_pmo.core.i18n import tr

ROLES = ("viewer", "operator", "approver", "admin")
PUBLIC_PATHS = {"/health", "/docs", "/docs/oauth2-redirect", "/redoc", "/openapi.json"}
MIN_KEY_LENGTH = 16


@dataclass(frozen=True)
class Principal:
    subject: str
    roles: frozenset[str] = field(default_factory=frozenset)

    def has(self, role: str) -> bool:
        return "admin" in self.roles or role in self.roles or role == "viewer"


ANONYMOUS = Principal("anonymous", frozenset(ROLES))


class Authenticator(Protocol):
    def authenticate(self, request: Request) -> Principal | None:
        """Return who sent the request, or None if the credentials are missing or wrong."""
        ...


class AuthConfigError(ValueError):
    """Raised at startup when auth is switched on but not configured correctly."""


def _presented_key(request: Request) -> str:
    header = request.headers.get("authorization", "")
    if header.lower().startswith("bearer "):
        return header[7:].strip()
    return request.headers.get("x-api-key", "").strip()


class ApiKeyAuthenticator:
    def __init__(self, keys: dict[str, Principal]) -> None:
        if not keys:
            raise AuthConfigError(
                "MA_PMO_AUTH_MODE=api_key needs at least one MA_PMO_API_KEYS entry"
            )
        self._keys = keys

    @classmethod
    def parse(cls, spec: str) -> ApiKeyAuthenticator:
        keys: dict[str, Principal] = {}
        for entry in (e.strip() for e in spec.split(",")):
            if not entry:
                continue
            parts = entry.split(":", 2)
            if len(parts) != 3:
                raise AuthConfigError("each MA_PMO_API_KEYS entry is name:role+role:key")
            name, roles_text, key = (p.strip() for p in parts)
            roles = frozenset(r.strip() for r in roles_text.split("+") if r.strip())
            unknown = roles - set(ROLES)
            if not name or not roles or unknown:
                raise AuthConfigError(f"API key '{name}': roles must be from {', '.join(ROLES)}")
            if len(key) < MIN_KEY_LENGTH:
                raise AuthConfigError(
                    f"API key '{name}' is shorter than {MIN_KEY_LENGTH} characters"
                )
            if key in keys:
                raise AuthConfigError(f"API key for '{name}' is used twice")
            keys[key] = Principal(name, roles)
        return cls(keys)

    def authenticate(self, request: Request) -> Principal | None:
        presented = _presented_key(request)
        if not presented:
            return None
        # compare against every key in constant time so timing does not reveal a prefix
        found = None
        for key, principal in self._keys.items():
            if hmac.compare_digest(presented.encode(), key.encode()):
                found = principal
        return found


def _load_custom(settings: Settings) -> Authenticator:
    target = settings.authenticator
    if ":" not in target:
        raise AuthConfigError("MA_PMO_AUTHENTICATOR must look like package.module:factory")
    module_name, attr = target.split(":", 1)
    module = importlib.import_module(module_name)
    factory: Callable[[Settings], Authenticator] = getattr(module, attr)
    return factory(settings)


def build_authenticator(settings: Settings) -> Authenticator | None:
    """None means auth is off."""
    mode = settings.auth_mode.strip().lower()
    if mode in ("", "off"):
        return None
    if mode == "api_key":
        return ApiKeyAuthenticator.parse(settings.api_keys)
    if mode == "custom":
        return _load_custom(settings)
    raise AuthConfigError(
        f"unknown MA_PMO_AUTH_MODE '{settings.auth_mode}' (off | api_key | custom)"
    )


def required_role(method: str, path: str) -> str | None:
    """The role a request needs, or None for public endpoints."""
    if method == "OPTIONS" or path in PUBLIC_PATHS:
        return None
    if method in ("GET", "HEAD"):
        return "viewer"
    if path.startswith("/approvals/"):
        return "approver"
    if path.startswith("/integrations/") and path.endswith("/test"):
        return "admin"
    return "operator"


class AuthMiddleware(BaseHTTPMiddleware):
    """Authenticates every request and enforces `required_role`; stores the Principal on
    `request.state.principal` for handlers (see `get_principal`)."""

    def __init__(self, app, authenticator: Authenticator | None = None) -> None:  # type: ignore[no-untyped-def]
        super().__init__(app)
        self.authenticator = authenticator

    async def dispatch(self, request: Request, call_next) -> Response:  # type: ignore[no-untyped-def]
        if self.authenticator is None:
            request.state.principal = ANONYMOUS
            return await call_next(request)
        role = required_role(request.method, request.url.path)
        principal = self.authenticator.authenticate(request)
        if role is None:
            request.state.principal = principal or Principal("anonymous")
            return await call_next(request)
        if principal is None:
            return JSONResponse(
                {"detail": tr("authentication required: send an API key",
                              "인증이 필요합니다: API 키를 보내 주세요")},
                status_code=401, headers={"WWW-Authenticate": "Bearer"},
            )
        if not principal.has(role):
            return JSONResponse(
                {"detail": tr(f"'{principal.subject}' needs the '{role}' role",
                              f"'{principal.subject}'에게 '{role}' 역할이 필요합니다")},
                status_code=403,
            )
        request.state.principal = principal
        return await call_next(request)


def get_principal(request: Request) -> Principal:
    """FastAPI dependency: the authenticated user (ANONYMOUS when auth is off)."""
    return getattr(request.state, "principal", ANONYMOUS)


# handler parameter type: `def view(principal: CurrentPrincipal)`
CurrentPrincipal = Annotated[Principal, Depends(get_principal)]

