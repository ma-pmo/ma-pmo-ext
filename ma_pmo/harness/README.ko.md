# MA-PMO 실험 하네스

**[English](README.md) | 한국어**

> 영문 문서가 기준이며, 이 문서는 한국어 번역본입니다.


시나리오·에이전트·KPI·가설 위에서 **프로그래밍 가능한 실험**을 정의·실행·리포트하는 프레임워크.
논문 실증(H1~H5)·ablation·회귀 측정을 재현 가능하게 자동화한다. (in-process, API/키 불필요)

## 구조

```
ma_pmo/harness/
├─ spec.py            # ExperimentSpec + Experiment(fluent 빌더)
├─ runner.py          # run_experiment: 배치·반복·ablation 실행
├─ collectors.py      # 트레이스→측정치 추출, 집계, 가설 커버리지
├─ reporters.py       # Markdown/JSON/CSV 리포트
├─ experiments/       # 사전 정의 실험 (EXPERIMENTS 레지스트리)
│  ├─ full_suite.py         # 20개 시나리오 전체 스윕
│  ├─ hypothesis_matrix.py  # H1~H5 커버리지 + 반복 3회 분산
│  └─ a7_ablation.py        # A7 지식 ablation (H4)
├─ cli.py             # ma-pmo harness <experiment>
└─ results/           # 산출물(.md/.json/.csv) — gitignore
```

## CLI 사용

```bash
ma-pmo harness list                  # 실험 목록
ma-pmo harness full_suite            # 전체 스윕 → Markdown 출력
ma-pmo harness hypothesis_matrix --save   # 결과를 harness/results/ 에 저장
MA_PMO_LANG=ko ma-pmo harness a7_ablation --save  # 한국어 ablation 리포트
make harness                              # = full_suite --save
```

## 프로그래밍 API

```python
from ma_pmo.harness import Experiment, run_experiment, render_markdown, write_report

# 선언적 실험 정의 (fluent)
spec = (
    Experiment("my_exp", "커스텀 실험")
    .with_scenarios("quarterly_review", "risk_rebalance")  # 생략 시 전체 20개
    .repeat(5)                # 반복(분산 분석)
    .ablate("A7")             # 에이전트 제외 비교
    .on_scope("PORTFOLIO#2026-Q1")
)

result = run_experiment(spec)
print(render_markdown(result))     # 논문용 표
write_report(result)               # md/json/csv 저장
```

## 리포트 산출물

- **가설 커버리지 매트릭스**: H1~H5 × 검증 시나리오
- **시나리오별 요약**: 에이전트·소요시간(평균±std)·산출·메시지·게이트 수
- **Ablation**: 에이전트 제외 시 산출·발견 변화 (예: A7 제거 시 citation 손실)
- **원자료**: 모든 실행 트레이스 측정치 (JSON), 스프레드시트용 CSV

## 확장

1. `ma_pmo/harness/experiments/<name>.py` 에 `spec = Experiment(...)...` 정의
2. `ma_pmo/harness/experiments/__init__.py` 의 `EXPERIMENTS` 에 등록
3. `ma-pmo harness <name>` 로 실행

새 측정치가 필요하면 `collectors.collect_run` 에 추출 로직을, 표가 필요하면 `reporters.render_markdown` 에 섹션을 추가한다.
