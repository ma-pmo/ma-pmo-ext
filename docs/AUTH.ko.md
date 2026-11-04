# API 인증

**[English](AUTH.md) | 한국어**

API는 설치 직후 데모와 대시보드가 바로 동작하도록 인증이 **꺼진** 상태로 배포됩니다. 다른 사람이
API에 접근할 수 있게 되기 전에, 특히 승인 API를 열기 전에 반드시 켜세요.

## 모드

| `MA_PMO_AUTH_MODE` | 호출자 | 용도 |
|---|---|---|
| `off` (기본값) | 모든 역할을 가진 익명 사용자 | 로컬 개발, 데모 |
| `api_key` | `MA_PMO_API_KEYS`에 등록된 키의 주인 | 소규모 팀, 스크립트, CI, MCP 클라이언트 |
| `custom` | 직접 만든 인증기가 돌려주는 사용자 | SSO/OIDC, JWT, 인증 프록시 |

설정이 잘못되면 API가 실수로 열린 채 돌지 않고, 시작할 때 명확한 오류를 내고 멈춥니다.

## 역할

| 역할 | 할 수 있는 일 |
|---|---|
| `viewer` | 모든 조회(`GET`) |
| `operator` | 조회, 에이전트·시나리오 실행, 웹훅 전송(`POST`) |
| `approver` | 조회, HITL 결정 승인·반려(`POST /approvals/{id}`) |
| `admin` | 연동 테스트 전송을 포함한 모든 것 |

모든 역할은 조회할 수 있습니다. 키 하나에 역할을 여러 개 줄 수 있습니다: `operator+approver`.
`/health`, `/docs`, `/redoc`, `/openapi.json`, CORS 사전 요청은 항상 공개입니다.

인증이 켜져 있으면 **결정에 기록되는 승인자는 인증된 사용자**입니다. 요청 본문의 `approver` 값은
무시되므로 다른 사람 이름으로 승인할 수 없습니다.

## API 키

```bash
openssl rand -hex 24          # 사람이나 시스템마다 키 하나씩 생성
```

```bash
MA_PMO_AUTH_MODE=api_key
MA_PMO_API_KEYS=alice:approver:<키1>,ci-bot:operator:<키2>,dash:viewer+approver:<키3>
```

항목 형식은 `이름:역할+역할:키`입니다. 키는 16자 이상이고 서로 달라야 합니다. 둘 중 한 헤더로
보냅니다.

```bash
curl -H "Authorization: Bearer <키>" localhost:8000/kpi
curl -H "X-API-Key: <키>" localhost:8000/auth/whoami     # 내가 누구이고 어떤 역할인지
```

키를 바꿀 때는 새 항목을 추가하고, 클라이언트를 새 키로 바꾼 뒤, 옛 항목을 지우고 API를 다시
시작하세요.

## 대시보드

대시보드(`apps/web`)의 `NEXT_PUBLIC_API_KEY`에 `viewer` 역할(대시보드에서 승인한다면 `approver`도)
키를 넣으세요. 이 키는 대시보드를 여는 누구에게나 보이므로 대시보드는 내부망이나 SSO 프록시 뒤에
두세요. 대시보드의 일반 링크(HTML 보고서, 양식 다운로드)는 헤더를 보낼 수 없으니 같은 프록시를
통해 여세요.

## 직접 만든 인증기

```python
# my_company/auth.py
from ma_pmo.api.auth import Principal

class GatewayAuth:
    """API 앞의 인증 프록시가 넣어 준 사용자 헤더를 신뢰합니다."""

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

전달된 헤더는 API가 *오직* 그 프록시를 통해서만 접근 가능할 때만 신뢰하세요.

## 코드 위치

- `ma_pmo/api/auth.py` — `AuthMiddleware`, `required_role()`(경로별 정책), `Principal`,
  `ApiKeyAuthenticator`, `build_authenticator()`.
- 핸들러에서 호출자가 필요하면 `principal: CurrentPrincipal`로 받습니다.
- 테스트: `tests/test_auth.py`.
