# 7. 연동과 장애 격리

**[English](07-integrations.md) | 한국어** · [과정 지도](README.ko.md) · 실습: [알림](../../ma_pmo/learn/labs/lab1_notifier/README.ko.md) · [트래커](../../ma_pmo/learn/labs/lab4_tracker/README.ko.md)

## 목표

조직이 이미 쓰는 도구(메신저, 웹훅, 이슈 트래커)에 좁은 플러그인 계약으로 에이전트를 연결해서, 연동이
망가져도 에이전트는 절대 멈추지 않게 합니다.

## 개념

연동은 양방향입니다.

- **나가는 쪽(알림, notifier)** — 이벤트가 시스템 밖으로 나갑니다: "승인 요청", "고위험 리스크 탐지",
  "게이트 미통과", "보고서 준비".
- **들어오는 쪽(트래커, tracker)** — 데이터가 시스템으로 들어옵니다: 프로젝트, 태스크, 진척, 의존 관계.

두 규칙이 안전을 지킵니다.

1. **좁은 접점.** 알림은 `name`과 `send(event)`만 있습니다. 트래커는
   `get_portfolio_status(portfolio_id) -> dict`만 있습니다. 에이전트는 Slack이나 Jira가 아니라 이
   접점에 의존하므로 연동을 바꾸고, 가짜로 대체하고, 따로 테스트할 수 있습니다.
2. **최선 노력 전달.** 알림이 실패하면 디스패처가 잡아서 *기록*하고, 에이전트 실행은 계속됩니다. 알림
   자신은 오류를 삼키면 안 됩니다. 그러면 웹훅이 망가졌다는 걸 아무도 모릅니다.

## MA-PMO에서는

- `ma_pmo/integrations/base.py` — `Event`, `EventType`, `Notifier` 프로토콜, `IntegrationSpec`
  (이름, 종류, 필요한 설정, 생성 함수).
- `ma_pmo/integrations/registry.py` — 기본 연동(Slack, 웹훅, Jira)과 `ma_pmo.integrations`
  entry point로 들어온 플러그인. `MA_PMO_INTEGRATIONS=slack,jira`로 켜고, 켜진 트래커가 없으면 데모
  데이터를 씁니다.
- `ma_pmo/integrations/dispatch.py` — `emit()`이 각 이벤트를 각 알림에 보내고 시도마다
  `ok: true/false` 한 줄을 돌려줍니다.
- `ma_pmo/connectors/jira_mock.py`와 `ma_pmo/integrations/jira.py` — 출처는 달라도 같은 형태를
  돌려주는 트래커 두 개.
- `GET /integrations`는 무엇이 켜졌고 설정됐는지 보여 줍니다(비밀 값은 절대 안 보임).
  `POST /integrations/{name}/test`는 테스트 이벤트를 보냅니다.
- 같은 접점의 확장: GitHub·Linear 트래커는 Jira와 같은 프로젝트 규칙
  (`ma_pmo/integrations/mapping.py`)을 쓰고, `.ics` 캘린더는 A3에 바쁜 시간을 넣고
  (`connectors/calendar.py`), MCP 서버(`ma_pmo/mcp_server.py`)는 에이전트를 AI 어시스턴트의 도구로
  내보냅니다. 승인은 일부러 도구에서 뺐습니다.

## 해보기

```bash
curl -s localhost:8000/integrations | python -m json.tool
MA_PMO_INTEGRATIONS=webhook MA_PMO_WEBHOOK_URL=http://localhost:9/nowhere ma-pmo serve --port 8001 &
curl -s -X POST localhost:8001/integrations/webhook/test   # 실패하지만 API는 계속 동작
```

## 흔한 실수

- **재시도 폭주.** 에이전트 실행 안에서 죽은 웹훅을 재시도하면 장애 하나가 모든 에이전트를 느리게
  만듭니다. 타임아웃으로 빨리 실패하고, 재시도가 필요하면 실행 밖에서 하세요.
- **비밀 노출.** 상태 API는 *어떤* 설정이 빠졌는지만 말하고 값은 절대 보여 주지 않습니다.
- **"없음"을 예외로.** 없는 포트폴리오를 요청받은 트래커는 죽지 않고 `found: False`를 돌려줍니다.
  에이전트가 판단할 수 있는 데이터입니다.

## 실습

- [실습 1 — 알림 플러그인 만들기](../../ma_pmo/learn/labs/lab1_notifier/README.ko.md):
  `ma-pmo learn start 1`.
- [실습 4 — 나만의 트래커 만들기](../../ma_pmo/learn/labs/lab4_tracker/README.ko.md):
  `ma-pmo learn start 4`.
- [실습 5 — MCP 도구 만들기](../../ma_pmo/learn/labs/lab5_mcp_tool/README.ko.md):
  `ma-pmo learn start 5` (`pip install "ma-pmo[mcp]"` 필요).

## 점검 질문

1. Slack 알림이 이벤트마다 5초 뒤 타임아웃됩니다. 시나리오 실행은 어떻게 보이고, 로그에는 무엇이 남나요?
2. `IntegrationSpec`이 값을 직접 읽지 않고 필요한 *설정 이름*을 나열하는 이유는?
3. 동료가 "딱 이번만" A4가 Jira를 직접 부르게 하자고 합니다. 무엇을 잃게 되나요?

다음: [8. 에이전트 운영하기](08-operating-agents.ko.md)
