# LLM 비용

**[English](COSTS.md) | 한국어**

모든 LLM 호출은 비용 원장에 기록됩니다. 어느 실행의 어느 단계인지, 에이전트, 모델, 제공자가 알려 준 토큰,
그리고 USD 비용이 남습니다. LLM이 없는 에이전트나 API 키 없이 실행할 때는 결정론적 방식으로 동작하므로
비용이 들지 않습니다.

## 어디서 보나요

- 대시보드 → **비용**: 합계와 모델·에이전트·워크플로·날짜·실행별 비용. 최근 7·30·90일 또는 전체.
- `GET /costs?by=model|agent|workflow|run|day&days=30`: 같은 내용의 JSON.
- `GET /runs/{run_id}/costs`: 실행 하나의 단계별 비용.

다른 데이터처럼 원장도 워크스페이스별로 나뉩니다(Postgres에서는 행 수준 보안 적용).

## 가격

가격은 버전이 있는 가격표에서 가져오고, 원장의 각 행에 어느 가격표로 계산했는지 남습니다.

1. `MA_PMO_PRICE_TABLE`이 가리키는 직접 만든 JSON 파일
2. 없으면 설치된 LiteLLM에 포함된 가격표(버전이 `uv.lock`에 고정되어 있어, 업그레이드하면 변경이 드러남)

두 가격표 모두 모르는 모델은 **가격을 매기지 않습니다**. 그 호출은 "가격 미상 호출"로 따로 세고 USD
합계에서 빼며, 추정하지 않습니다. 로컬 모델(Ollama)은 LiteLLM이 0원으로 계산합니다.

직접 만드는 가격표는 100만 토큰당 USD입니다(`cache_read`, `cache_write`를 생략하면 `input`과 같음).

```json
{"version": "acme-2026-11",
 "models": {
   "anthropic/claude-sonnet-5": {"input": 3.0, "output": 15.0, "cache_read": 0.3, "cache_write": 3.75},
   "acme/in-house-model": {"input": 0.4, "output": 0.4}
 }}
```

모델은 적힌 이름 그대로 찾고, `provider/name` 형식이면 `name`으로도 찾습니다.

## 토큰 계산 방식

원장은 LiteLLM이 알려 주는 제공자 사용량을 그대로 둡니다. `prompt_tokens`에는 프롬프트 캐시에서 읽거나
캐시에 쓴 입력도 들어 있으며, 이 둘은 따로도 기록합니다(`cache_read_tokens`, `cache_write_tokens`).
가격 계산은 다음과 같습니다.

```
(prompt - 캐시 읽기 - 캐시 쓰기) × input + 캐시 읽기 × cache_read
  + 캐시 쓰기 × cache_write + completion × output
```

같은 응답에 대해 LiteLLM의 `completion_cost`와 결과가 같으며, 테스트가 캐시가 있는 경우와 없는 경우의
제공자 형식 사용량으로 이를 확인합니다. 재시도한 호출도 실제로 돈이 드므로 다시 셉니다. 기록이 실패해도
에이전트의 호출은 멈추지 않고 경고만 로그에 남습니다.
