# 2. 계약으로서의 구조화 메시지

**[English](02-structured-messages.md) | 한국어** · [과정 지도](README.ko.md)

## 목표

MA-PMO의 에이전트가 대화체 대신 검증되고 버전이 붙은 메시지로 소통하는 이유와, 추가 전용 로그가
주는 이점을 이해합니다.

## 개념

에이전트 사이의 자유 텍스트는 명세 없는 API입니다. 한쪽이 표현을 바꾸는 순간 깨집니다. **계약**은
세 가지를 고정합니다.

1. **형태** — 어떤 필드가 있고 타입은 무엇인지(바라는 게 아니라 검증합니다).
2. **버전** — `risk_alert.v1`. 호환되지 않는 변경은 `v2`가 되고, 둘이 함께 존재할 수 있습니다.
3. **메타데이터** — 누가, 누구에게, 왜(`intent`), 무엇에 관해(`task_ref`), 얼마나 확신하며
   (`confidence`) 보냈는지.

자연어도 쓸 자리가 있습니다. 보고서 요약 같은 필드 *안*입니다. 하지만 그것을 감싸는 봉투는 기계가
검사합니다.

## MA-PMO에서는

- `ma_pmo/core/schemas/message.py` — `AgentMessage`: `sender`, `receiver`, `intent`
  (`request` / `inform` / `propose` / `approve`), `task_ref`, `payload`, `confidence`,
  `human_gate_required`. `MessagePayload`는 버전 없는 스키마 이름을 거부합니다.
- `ma_pmo/core/schemas/payloads/` — 페이로드마다 Pydantic 모델(`schedule.v1`, `risk_alert.v1`,
  `report.v1` 등). `protocol.validate_payload`가 데이터를 검사합니다.
- `ma_pmo/core/protocol.py` — `publish()`가 검증하고, **추가 전용** 테이블에 메시지를 쌓고, 필요하면
  승인 대기열에 올립니다(4강).
- `BaseAgent.structured()`(`ma_pmo/agents/base.py`)는 LLM에게 에이전트 스키마로 파싱되는 출력을
  요구합니다. 모델 출력에도 같은 계약이 적용됩니다.

## 왜 추가 전용인가

고칠 수 있는 감사 로그는 일기장입니다. 추가 전용이면 모든 결정을 다시 따라가 볼 수 있습니다. 누가
어떤 확신도로 무엇을 제안했고, 그다음 무슨 일이 있었는지. 이후 상태(승인, 반려)는 메시지를 고치지
않고 *옆에* 기록합니다.

## 해보기

```bash
curl -s 'localhost:8000/messages?task_ref=PORTFOLIO%232026-Q1' | python -m json.tool | head -40
```

Python 셸에서 일부러 계약을 깨 보세요.

```python
from ma_pmo.core.schemas.message import MessagePayload
MessagePayload(schema="risk_alert", data={})   # ValueError: 버전 필요
```

## 흔한 실수

- **전부 선택 필드.** 모든 필드가 선택이면 쓰레기도 통과합니다.
- **얼떨결에 버전 변경.** 필드 이름을 그 자리에서 바꾸면 기존 소비자가 깨집니다. `v2`를 추가하세요.
- **장식용 확신도.** 아무도 `confidence`를 읽지 않으면 잡음입니다. MA-PMO에서는 사람 승인이 필요한지
  를 결정합니다(4강).

## 점검 질문

1. A4가 리스크 경보에 `mitigation_owner`를 추가하려 합니다. 새 버전이 필요할까요? 이유는?
2. 감사 로그로는 답할 수 있지만 애플리케이션 로그로는 답할 수 없는 질문은?
3. 형식이 틀린 LLM 출력은 어디서 잡히고, 그다음엔 어떻게 되나요? (3강)

다음: [3. 결정론적 대체 경로](03-offline-fallbacks.ko.md)
