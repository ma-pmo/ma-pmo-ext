# API authentication

**English | [한국어](AUTH.ko.md)**

The API ships with authentication **off**, so the demo and the dashboard work right after
install. Before anyone else can reach the API — especially the approval endpoint — turn it on.

## Modes

| `MA_PMO_AUTH_MODE` | Who is the caller | Use for |
|---|---|---|
| `off` (default) | an anonymous user with every role | local development and demos |
| `api_key` | the owner of the key in `MA_PMO_API_KEYS` | small teams, scripts, CI, MCP clients |
| `custom` | whatever your authenticator returns | SSO/OIDC, JWT, an identity-aware proxy |

A misconfigured mode stops the API at startup with a clear error, instead of running open by
accident.

## Roles

| Role | Can |
|---|---|
| `viewer` | read everything (`GET`) |
| `operator` | read, run agents and scenarios, send webhooks (`POST`) |
| `approver` | read, approve or reject HITL decisions (`POST /approvals/{id}`) |
| `admin` | everything, including integration test sends |

Every role can read. A key can hold several roles: `operator+approver`. `/health`, `/docs`,
`/redoc`, `/openapi.json` and CORS preflight requests are always public.

When auth is on, **the approver recorded on a decision is the authenticated user**. The
`approver` field in the request body is ignored, so nobody can sign in someone else's name.

## API keys

```bash
openssl rand -hex 24          # make a key per person or system
```

```bash
MA_PMO_AUTH_MODE=api_key
MA_PMO_API_KEYS=alice:approver:<key1>,ci-bot:operator:<key2>,dash:viewer+approver:<key3>
```

Each entry is `name:role+role:key`. Keys must be at least 16 characters and unique. Send one
with either header:

```bash
curl -H "Authorization: Bearer <key>" localhost:8000/kpi
curl -H "X-API-Key: <key>" localhost:8000/auth/whoami     # who am I, which roles
```

Rotate a key by adding the new entry, switching the client, then removing the old entry and
restarting the API.

## Dashboard

Set `NEXT_PUBLIC_API_KEY` for the dashboard (`apps/web`) to a key with `viewer` (and
`approver`, if people approve from it). The key is visible to anyone who can open the
dashboard, so keep the dashboard on a private network or behind your SSO proxy. Plain links in
the dashboard (HTML report, template downloads) cannot send the header; open them through the
same proxy.

## Custom authenticator

```python
# my_company/auth.py
from ma_pmo.api.auth import Principal

class GatewayAuth:
    """Trusts the user header set by an identity-aware proxy in front of the API."""

    def authenticate(self, request):
        user = request.headers.get("x-forwarded-user")
        if not user:
            return None
        roles = {"viewer", "approver"} if user.endswith("@pmo.example.com") else {"viewer"}
        return Principal(user, frozenset(roles))

def factory(settings):
    return GatewayAuth()
```

```bash
MA_PMO_AUTH_MODE=custom
MA_PMO_AUTHENTICATOR=my_company.auth:factory
```

Only trust a forwarded header when the API is reachable *only* through that proxy.

## In code

- `ma_pmo/api/auth.py` — `AuthMiddleware`, `required_role()` (route policy), `Principal`,
  `ApiKeyAuthenticator`, `build_authenticator()`.
- In a handler, take the caller with `principal: CurrentPrincipal`.
- Tests: `tests/test_auth.py`.
