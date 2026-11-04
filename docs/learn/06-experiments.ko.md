# 6. 실험, 제거 실험(ablation), 테스트

**[English](06-experiments.md) | 한국어** · [과정 지도](README.ko.md) · 실습: [제거 실험 설계](../../ma_pmo/learn/labs/lab3_ablation/README.ko.md)

## 목표

시스템에 관한 주장을 재현 가능하게 만듭니다. 실험을 코드로 선언하고, 제거 실험으로 에이전트 하나의
기여를 분리하고, smoke·회귀 테스트로 동작을 고정합니다.

## 개념

- **코드로서의 실험.** 어떤 시나리오를, 몇 번, 어느 포트폴리오에서, 어떤 에이전트를 빼고 돌리는지를
  검토하고 버전 관리하고 다시 돌릴 수 있는 파일에 적습니다. 노트북 셀이 아닙니다.
- **제거 실험(ablation).** 구성 요소 하나를 빼고 나머지는 그대로 둔 채 비교합니다. 결과가 바뀌지
  않으면 그 요소가 주장대로 일하지 않거나, 시나리오가 그 요소를 아예 쓰지 않는 것입니다.
- **결정론적 실행.** 3강의 대체 경로 덕분에 오프라인 실행은 두 번 돌려도 같은 답입니다. 이때 반복은
  아무것도 측정하지 않습니다. LLM이 끼면 반복이 분산을 측정합니다.
- **두 종류의 테스트.** *Smoke* 테스트는 "주요 경로가 처음부터 끝까지 아직 동작하나?"를 몇 초 안에
  묻습니다. *회귀* 테스트는 알려진 데이터의 알려진 결과("데모 포트폴리오에서 PROJ-31은 red")를 고정하고,
  동작을 일부러 바꿀 때만 실패해야 합니다.

## MA-PMO에서는

- `ma_pmo/harness/spec.py` — `Experiment` 빌더: `.with_scenarios(...)`, `.repeat(n)`,
  `.ablate("A7")`, `.on_scope(...)`.
- `ma_pmo/harness/runner.py` — `run_experiment()`가 시나리오 × 반복을 돌리고, 제거 실험이면 **그
  에이전트를 쓰는 시나리오에 한해** 기준 실행과 제거 실행을 비교합니다.
- `ma_pmo/harness/experiments/` — 기본 실험(`a7_ablation`, `hypothesis_matrix`, `full_suite`).
  `./experiments`의 파일은 자동으로 인식됩니다.
- `ma-pmo harness new my_exp --hypothesis H3`는 실험과 그 테스트를 함께 만들고, "아무것도 바꾸지
  않는" 제거 실험은 거부합니다.
- 테스트: `tests/test_smoke.py`, `tests/test_regression.py`, 마커 `smoke`·`regression`,
  `make test-smoke`, `make test-regression`. CI는 smoke → 회귀 → 전체 순서로 돌립니다.

## 해보기

```bash
ma-pmo harness list
ma-pmo harness a7_ablation
ma-pmo harness new risk_focus --hypothesis H3 --repeat 3
```

## 흔한 실수

- **시나리오가 부르지도 않는 에이전트 제거.** 결과는 "차이 없음"이고, 사실이지만 쓸모없습니다.
  `ma-pmo learn scenarios`로 시나리오별 에이전트를 확인하세요.
- **잡음을 고정하는 회귀 테스트.** 안정적이어야 하는 것(개수, 판정, 임계경로)을 고정하고, 시각이나
  LLM 문장은 고정하지 마세요.
- **질문 없는 실험.** 설명에 가설부터 쓰세요.

## 실습

[실습 3 — 제거 실험 설계하기](../../ma_pmo/learn/labs/lab3_ablation/README.ko.md):
`ma-pmo learn start 3`. A7의 기여를 보여 주는 H4 실험을 작성합니다.

## 점검 질문

1. A4를 제거했는데 발견 사항에 변화가 없습니다. 가능한 이유 세 가지는?
2. 회귀 테스트에 들어갈 것은: red 프로젝트 수, 아니면 보고서 첫 문장?
3. `repeat`를 1보다 크게 할 때는 언제인가요?

다음: [7. 연동과 장애 격리](07-integrations.ko.md)
