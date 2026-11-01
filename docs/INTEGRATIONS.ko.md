# 연동(Integrations)

**[English](INTEGRATIONS.md) | 한국어**

> 영문 문서가 기준이며, 이 문서는 한국어 번역본입니다.

MA-PMO는 팀이 이미 쓰는 도구와 작은 플러그인 형태로 연결됩니다.
코드 수정 없이 **환경 변수만으로** 켜고 끌 수 있습니다.

| 이름 | 종류 | 하는 일 |
|---|---|---|
| `slack` | 알림(notifier) | 승인 요청, 고위험 리스크, 게이트 미통과, 보고서 생성을 Slack 채널로 보냄 |
| `webhook` | 알림(notifier) | 모든 이벤트를 JSON으로 원하는 URL에 POST (n8n, Zapier, Make, 자체 서비스) |
| `jira` | 데이터(tracker) | 데모 데이터 대신 Jira Cloud의 실제 프로젝트·이슈를 에이전트가 읽음 |

- **알림(notifier)**: 이벤트를 받아 바깥으로 보냅니다. 여러 개를 동시에 켤 수 있습니다.
- **데이터(tracker)**: 에이전트가 포트폴리오 정보를 읽어오는 곳입니다. 한 번에 하나만 쓰며, 없으면 기본 데모 포트폴리오를 씁니다.
- 연동은 **실패해도 멈추지 않습니다**: Slack이 장애이거나 URL이 틀려도 오류만 기록하고 에이전트는 계속 동작합니다.

## 빠른 시작

```bash
# .env
MA_PMO_INTEGRATIONS=slack,jira
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/T000/B000/XXXX
JIRA_BASE_URL=https://your-team.atlassian.net
JIRA_EMAIL=you@company.com
JIRA_API_TOKEN=...
JIRA_PROJECT_KEYS=PAY,DATA
```

API를 다시 시작한 뒤 확인·테스트합니다.

```bash
curl localhost:8000/integrations              # 켜짐/설정 완료 여부 (비밀값은 표시 안 함)
curl -X POST localhost:8000/integrations/slack/test   # 테스트 메시지 전송
```

## 이벤트 종류

| 이벤트 | 발생 시점 |
|---|---|
| `approval.requested` | 메시지가 사람 승인 큐로 들어갈 때 |
| `approval.resolved` | 누군가 승인 또는 반려했을 때 |
| `risk.detected` | A4가 리스크를 `high`/`critical`로 판정했을 때 |
| `gate.failed` | A6 스테이지 게이트 심사가 fail일 때 |
| `report.generated` | A5가 경영 보고서를 만들었을 때 |
| `integration.test` | `POST /integrations/{name}/test` 호출 시 |

보낼 이벤트를 줄이려면 `MA_PMO_NOTIFY_EVENTS=approval.requested,risk.detected`처럼 설정합니다(비우면 전부).
알림 제목은 요청 언어(`?lang=ko`) 또는 `MA_PMO_LANG`을 따르고, 메시지 속 대시보드 링크는 `MA_PMO_PUBLIC_URL`로 정합니다.

## Slack

1. Slack에서 **앱 → Incoming Webhooks → Slack에 추가** → 채널 선택 → URL 복사
   ([공식 안내](https://api.slack.com/messaging/webhooks))
2. `SLACK_WEBHOOK_URL`에 붙여넣고 `MA_PMO_INTEGRATIONS`에 `slack` 추가

메시지는 제목, 상세 내용, 이벤트 종류·프로젝트, "Open MA-PMO" 버튼으로 구성됩니다.

## 범용 웹훅

`MA_PMO_WEBHOOK_URL`을 설정하고 `webhook`을 추가합니다. 형식은 [영문 문서](INTEGRATIONS.md#generic-webhook)의 JSON 예시와 같습니다.

## Jira Cloud

1. <https://id.atlassian.com/manage-profile/security/api-tokens> 에서 API 토큰을 만듭니다.
2. `JIRA_BASE_URL`, `JIRA_EMAIL`, `JIRA_API_TOKEN`, `JIRA_PROJECT_KEYS`를 설정하고
   `MA_PMO_INTEGRATIONS`에 `jira`를 추가합니다. 프로젝트 키 하나가 MA-PMO 프로젝트 하나가 됩니다.
3. 선택: 스토리 포인트를 공수로 쓰려면 `JIRA_STORY_POINTS_FIELD=customfield_10016`

Jira 데이터 변환 규칙:

| MA-PMO | Jira |
|---|---|
| 태스크 공수(시간) | 최초 예상 시간 → 없으면 스토리 포인트 × 8 → 없으면 8 |
| 태스크 진척률 | 상태 분류: 완료 100%, 진행 중 = 시간 추적 %(없으면 50%), 할 일 0% |
| 선후행 관계 | "is blocked by" 링크 |
| 계획 시작일 | 가장 이른 이슈 생성일 |
| 계획 완료일 / 마감일 | 미완료 이슈의 가장 늦은 기한 / 전체 이슈의 가장 늦은 기한 |
| 상태색 | red: 기한이 지난 미완료 이슈 · amber: 막힌 이슈 · 그 외 green |

자원 마스터(사람·스킬·가용 시간)는 계속 MA-PMO 데이터베이스를 씁니다.

## 직접 연동 만들기

연동 하나는 `IntegrationSpec` 하나입니다. 어떤 Python 패키지든 `ma_pmo.integrations` entry point로
등록하면 이름으로 켤 수 있습니다. 예시 코드(Microsoft Teams 알림)는
[영문 문서](INTEGRATIONS.md#writing-your-own-integration)를 참고하세요.

- **알림**: `name`과 `send(event)`가 필요합니다. 실패하면 예외를 던지면 됩니다.
- **데이터**: `ma_pmo/connectors/jira_mock.py`와 같은 형태의 `get_portfolio_status(portfolio_id) -> dict`가 필요합니다.
- 기본 연동 코드는 `ma_pmo/integrations/`, 테스트 작성법은 `tests/test_integrations.py`에 있습니다.
