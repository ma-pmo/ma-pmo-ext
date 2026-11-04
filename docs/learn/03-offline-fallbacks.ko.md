# 3. 결정론적 대체 경로: 오프라인 우선

**[English](03-offline-fallbacks.md) | 한국어** · [과정 지도](README.ko.md)

## 목표

모델을 쓸 수 없거나, 느리거나, 틀려도 계속 동작하는 에이전트 단계를 설계하고, 그 덕분에 시스템이
테스트 가능해지는 이유를 봅니다.

## 개념

MA-PMO의 모든 LLM 단계에는 **결정론적 쌍둥이**가 있습니다. 같은 스키마의 올바른 출력을 만드는 규칙,
알고리즘, 템플릿입니다. LLM 경로는 결과를 낫게 하고, 대체 경로는 결과가 *있음*을 보장합니다.

```
try:   output = llm.complete_structured(prompt, Schema)   # 더 나은 문장, 판단
except: output = rules(data)                              # 항상 유효, 항상 제시간
```

세 가지가 따라옵니다.

1. **가용성** — 키가 없거나 공급자가 장애여도 품질만 떨어지고 서비스는 멈추지 않습니다.
2. **테스트 가능성** — CI가 네트워크 없이 전체 파이프라인을 돌리고, 두 번 돌려도 같은 답을 얻습니다.
3. **기준선** — 대체 경로가 곧 실험의 "LLM 없음" 조건입니다.

*절대* LLM을 부르면 안 되는 단계도 있습니다. 임계경로 일정 계산은 산수입니다. MA-PMO는 프롬프트가
아니라 CPM(`ma_pmo/agents/cpm.py`)으로 계산합니다.

## MA-PMO에서는

- `ma_pmo/agents/orchestrator.py` → `orchestrator_rules.py`: LLM 호출이 실패하면 규칙 기반 라우팅과
  종합(로그에서 `route_fallback`, `synthesize_fallback`을 찾아보세요).
- `ma_pmo/agents/reporting.py`: `_fallback_report()`가 데이터로 경영 보고서를 만듭니다.
- `ma_pmo/agents/knowledge.py`: 생성이 불가능하면 교훈 자료에서 출처를 단 추출형 답변.
- `ma_pmo/agents/cpm.py`, `allocation.py`, `gates.py`, `risk_signals.py`: 결정론적 핵심.

## 해보기

키 없이 평가를 돌려 봅니다.

```bash
env -u ANTHROPIC_API_KEY ma-pmo eval
```

모든 가설에 숫자가 나옵니다. 이제 `ma_pmo/agents/reporting.py`에서 보고서가 계속 나오게 하는
`except`를 찾아보세요.

## 흔한 실수

- **너무 많이 잡기.** 대체 경로는 *LLM의 실패*만 잡아야지, 내 코드의 버그까지 삼키면 안 됩니다.
  오케스트레이터처럼 오류를 로그로 남겨 대체 경로 사용이 숨지 않고 집계되게 하세요.
- **모양이 다른 대체 경로.** 같은 스키마를 돌려주지 않으면 가장 곤란한 순간에 소비자가 깨집니다.
- **차이를 재지 않음.** LLM 출력과 대체 출력을 비교하지 않으면 LLM의 가치를, 혹은 더 나쁜지를 알 수
  없습니다.

## 점검 질문

1. A5 보고서에서 LLM이 바꿔도 되는 필드와 반드시 데이터에서 와야 하는 필드는?
2. "하루 종일 대체 경로로 돌았다"를 어떻게 경보로 알리겠습니까?
3. 결정론적 대체 경로가 6강의 회귀 테스트를 가능하게 하는 이유는?

다음: [4. 사람 승인 게이트](04-human-in-the-loop.ko.md)
