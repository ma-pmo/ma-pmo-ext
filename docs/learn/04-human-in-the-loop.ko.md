# 4. 사람 승인 게이트(HITL)

**[English](04-human-in-the-loop.md) | 한국어** · [과정 지도](README.ko.md)

## 목표

어떤 에이전트 결정을 사람이 승인해야 하는지 정하고, 메시지 프로토콜 안에 게이트를 만들고, 그 비용을
측정합니다.

## 개념

자율성은 전부 아니면 전무가 아닙니다. 좋은 게이트는 이렇습니다.

- **선별적** — 일부 결정만 기다립니다. 영향이 큰 결정(예산, 범위, 인력, 대외 커뮤니케이션)이나
  확신도가 낮은 결정.
- **프로토콜에 내장** — 화면에 나중에 붙인 기능이 아닙니다. 메시지 자체가 사람이 필요하다고 말하므로
  어떤 소비자도 검사를 건너뛸 수 없습니다.
- **감사 가능** — 누가, 언제, 무엇을 보고 승인했는지.
- **측정됨** — 승인에는 시간이 듭니다. 승인 지연은 다른 비용처럼 추적합니다.

## MA-PMO에서는

- `AgentMessage.needs_human_gate(threshold)`(`ma_pmo/core/schemas/message.py`): 보낸 쪽이
  `human_gate_required`를 켰거나 `confidence`가 `HITL_CONFIDENCE_THRESHOLD`(기본 0.6)보다 낮으면 참.
- `protocol.publish()`가 메시지를 저장하고, 게이트 대상이면 `pending` 승인을 추가합니다.
- `ma_pmo/core/hitl.py` — `list_pending()`, `resolve(approval_id, approver, decision)`.
- API: `GET /approvals`, `POST /approvals/{id}`. 대시보드: 사이드바 **승인 큐**, 대기 건수 배지.
- 연동이 `approval.requested`, `approval.resolved`를 알려(7강) 사람들이 이미 쓰는 도구까지 게이트가
  닿습니다.

## 해보기

```bash
curl -s -X POST localhost:8000/demo/gated-message      # 확신도가 낮은 제안
curl -s localhost:8000/approvals | python -m json.tool  # 대기 중
```

대시보드(`make web` 후 http://localhost:3000/approvals?lang=ko)를 열어 승인하고 배지 숫자가 줄어드는
것을 확인하세요.

## 누가 승인했나?

API 인증을 켜면(`MA_PMO_AUTH_MODE=api_key`) `approver` 역할의 키만 승인을 처리할 수 있고, 기록되는
승인자는 요청 본문의 이름이 아니라 인증된 사용자입니다. [docs/AUTH.ko.md](../AUTH.ko.md) 참고.

## 기준값 고르기

너무 낮으면 위험한 조치가 빠져나가고, 너무 높으면 사람들이 쏟아지는 요청에 기계적으로 도장을 찍습니다.
후자가 더 나쁩니다. 안전해 *보이기* 때문입니다. 엄격하게 시작해서 승인 건수와 반려 비율을 재고, 결정
유형별로 완화하세요. 반려는 데이터입니다. 어느 에이전트의 확신도가 어긋나 있는지 보여 줍니다. [8강](08-operating-agents.ko.md)이 바로 그것을 측정합니다.

## 점검 질문

1. A3가 확신도 0.82로 한 사람을 두 프로젝트 사이에서 옮기자고 제안합니다. 게이트에 걸까요? 그 사람이
   유일한 데이터 엔지니어라면?
2. `human_gate_required`를 대시보드 코드가 아니라 메시지에 두는 이유는?
3. 승인 큐가 병목이 됐다는 것을 어떤 KPI로 알 수 있을까요?

다음: [5. 에이전트 측정하기](05-measuring-agents.ko.md)
