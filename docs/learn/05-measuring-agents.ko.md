# 5. 에이전트 측정하기: KPI, 가설, 기준선

**[English](05-measuring-agents.md) | 한국어** · [과정 지도](README.ko.md) · 실습: [데이터 고치기](../../ma_pmo/learn/labs/lab2_dataset/README.ko.md)

## 목표

"에이전트가 도움이 된다"를 검증할 수 있는 주장으로 바꾸고, 각 검증에 어떤 데이터가 필요한지 압니다.

## 개념

측정 가능한 주장에는 네 부분이 있습니다.

1. **가설** — "에이전트가 보고 주기를 줄인다"(H1).
2. **지표** — 실행마다 기록하는 보고 소요 시간(초).
3. **기준선** — 에이전트 *없이* 걸리는 시간. 이것이 없으면 어떤 숫자든 좋아 보입니다.
4. **판정 규칙** — 결과를 보기 *전에* 적어 둡니다. 감소폭이 양수면 지지, 목표에 못 미치면 부분 지지,
   비교할 것이 없으면 데이터 부족.

어떤 지표는 **정답 레이블**도 필요합니다. 리스크 탐지(H3)는 어느 프로젝트가 실제로 문제였는지 알려
주는 레이블과 비교해야만 의미가 있습니다. 레이블 없는 정밀도는 추측입니다.

## MA-PMO에서는

- **계측** — `ma_pmo/core/kpi.py`가 다섯 축(`time`, `resource`, `delivery`, `risk`, `cost`)에
  이벤트를 기록합니다. 에이전트가 일하면서 `kpi.record(...)`를 부르고(A2는 SPI와 예상 지연을 기록),
  `record_llm_cost`가 토큰과 지연을 추적합니다.
- **가설** — `ma_pmo/eval/harness.py`: H1 보고 시간, H2 유휴율, H3 리스크 탐지(레이블 대비
  정밀도/재현율/F1), H4 A7 제거 실험, H5 복잡성 층화.
- **판정** — `ma_pmo/eval/report.py`의 `summarize()`가 규칙을 적용합니다: 지지됨 / 부분 지지 /
  지지 안 됨 / 데이터 부족.
- **우리 데이터** — `ma-pmo template data`가 주장에 필요한 입력을 만듭니다: 프로젝트, 태스크, 자원,
  **baselines.json**, **risk_labels.csv**. `ma-pmo template validate`는 있을 수 없는 값이 그럴듯한
  결과로 둔갑하기 전에 막습니다.

같은 방법을 따르는 측정이 두 가지 더 있습니다. 승인 게이트의 **확신도 보정**
(`ma_pmo/eval/calibration.py`, 8강)과 라벨 질의로 본 A7의 **검색 품질**입니다.
`ma-pmo eval --retrieval`은 단어 검색과 벡터 검색의 recall@k와 MRR을 보여 줍니다.

## 해보기

```bash
ma-pmo eval                                       # 데모 포트폴리오 판정
ma-pmo template report --format html --out report.html
ma-pmo template data ./my-org && ma-pmo template validate ./my-org
ma-pmo eval --data ./my-org                       # 별도 DB, 섞이지 않음
```

## 흔한 실수

- **허공에서 온 기준선.** 누군가 짐작한 수작업 보고 시간이면 H1은 의미가 없습니다. 실제 몇 번을 재고
  어떻게 쟀는지 적어 두세요.
- **결과를 보고 규칙 바꾸기.** 기준을 먼저 정하세요(H3는 F1 ≥ 0.7이면 "지지").
- **데이터 섞기.** 우리 조직 데이터를 데모 DB에서 평가하면 두 포트폴리오가 섞입니다. 그래서 MA-PMO는
  `--data`를 별도 SQLite 파일에서 평가합니다.
- **숫자 하나로 다 말하기.** 판정 옆에 한계를 함께 적으세요. HTML 보고서에 그 섹션이 있습니다.

## 실습

[실습 2 — 조직 데이터 고치기](../../ma_pmo/learn/labs/lab2_dataset/README.ko.md):
`ma-pmo learn start 2`. 데이터를 지우지 않고 오류 7개를 고친 뒤 평가합니다.

## 점검 질문

1. H3의 정밀도가 1.0, 재현율이 0.33입니다. 무슨 일이 있었고 PMO에 뭐라고 말하겠습니까?
2. `baselines.json` 없이는 의미가 없는 가설은? `risk_labels.csv` 없이는?
3. 기본값 숫자보다 "데이터 부족"이 더 나은 판정인 이유는?

다음: [6. 실험, 제거 실험, 테스트](06-experiments.ko.md)
