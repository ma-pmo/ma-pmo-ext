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

## 자원 캘린더 (.ics)

A3는 회의·휴가·공휴일을 모르면 모든 사람이 매주 비어 있다고 보고 일을 배정합니다. 사람마다 자원 id를
파일 이름으로 한 iCalendar 파일을 폴더에 두고 지정하세요.

```bash
MA_PMO_CALENDAR_DIR=./calendars      # ./calendars/R-01.ics, ./calendars/R-02.ics, ...
```

파일은 어떤 캘린더 앱에서든 내보낼 수 있습니다(Google 캘린더: 설정 → 가져오기 및 내보내기, Outlook:
일정 저장, Apple 캘린더: 파일 → 내보내기). 그러면 A3가 사람별 바쁜 시간을 주간 가용 시간에서 빼고
배정하므로, 과부하가 캘린더에 맞게 드러납니다.

계산 규칙: 월~금만, 하루 최대 8시간까지 계산합니다. 종일 일정은 그날 전체를 막고, "한가함"으로 표시된
일정과 취소된 일정은 무시합니다. 시간은 파일에 적힌 그대로 계산하고(시간대 변환 없음), 반복 일정은 첫
회차만 계산하므로 반복을 펼친 상태로 내보내세요. 파일이 없는 사람은 완전히 비어 있다고 봅니다. 코드:
`ma_pmo/connectors/calendar.py` — 다른 출처를 쓰려면 `busy_hours(resource_id, week)`를 구현하세요.

## 과거 교훈 벡터 검색 (A7)

A7은 기본적으로 단어가 그대로 겹치는 교훈을 찾습니다. 벡터 검색으로 바꾸면 어형 변화와 조사가 붙은
한국어 단어도 찾고, 임베딩 모델을 연결하면 동의어까지 찾습니다.

```bash
MA_PMO_RETRIEVER=vector                          # 오프라인 문자 n-gram 벡터
MA_PMO_EMBEDDING_MODEL=ollama/nomic-embed-text   # 선택: LiteLLM이 지원하는 임베딩 모델
MA_PMO_EMBEDDING_API_BASE=http://localhost:11434 # 선택: 로컬·사내 엔드포인트
ma-pmo eval --retrieval                          # 라벨링된 질의로 recall@1, recall@3, MRR
```

기본 제공 질의 세트(`ma_pmo/fixtures/retrieval_eval.json`, 영어·한국어 14개)에서 오프라인 벡터는
recall@3을 0.857 → 1.0, MRR을 0.774 → 0.964로 올렸고, 향상분은 모두 조사가 붙은 한국어 질의입니다.
임베딩 모델에 연결할 수 없으면 A7은 어휘 검색으로 대체합니다(로그·추적·`--retrieval` 결과에 표시).
출처 인용은 항상 함께 나옵니다. 코드: `ma_pmo/connectors/vectordb.py`.

## 직접 연동 만들기

연동 하나는 `IntegrationSpec` 하나입니다. 어떤 Python 패키지든 `ma_pmo.integrations` entry point로
등록하면 이름으로 켤 수 있습니다. 예시 코드(Microsoft Teams 알림)는
[영문 문서](INTEGRATIONS.md#writing-your-own-integration)를 참고하세요.

- **알림**: `name`과 `send(event)`가 필요합니다. 실패하면 예외를 던지면 됩니다.
- **데이터**: `ma_pmo/connectors/jira_mock.py`와 같은 형태의 `get_portfolio_status(portfolio_id) -> dict`가 필요합니다.
- 기본 연동 코드는 `ma_pmo/integrations/`, 테스트 작성법은 `tests/test_integrations.py`에 있습니다.
