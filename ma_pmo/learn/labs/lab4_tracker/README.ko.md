# 실습 4 — 나만의 트래커 만들기

**[English](README.md) | 한국어** · 강의: [07 연동과 장애 격리](https://github.com/ma-pmo/ma-pmo-ext/blob/main/docs/learn/07-integrations.ko.md)

에이전트는 Jira나 데이터베이스, 스프레드시트를 직접 읽지 않습니다. `get_portfolio_status(portfolio_id)`
메서드 하나만 부르고 평범한 dict를 받습니다. 이 좁은 접점 덕분에 MA-PMO는 데모 데이터로도, Jira로도,
이번 실습이 끝나면 CSV 파일 폴더로도 돌아갑니다.

**익히는 것:** 데이터 계약을 정확히 구현하기, "없음"을 예외가 아닌 데이터로 다루기, 실제 에이전트
알고리즘(A2의 임계경로법)에 넣어 연동이 동작함을 증명하기.

## 파일

- `csv_tracker.py` — 이 파일만 고치면 됩니다.
- `data/` — 평가 양식 형식의 portfolio.csv, projects.csv, tasks.csv.

## 단계

1. **없을 때.** `portfolio_id`가 portfolio.csv에 없으면
   `{"portfolio_id": ..., "found": False, "projects": []}`를 돌려줍니다.
2. **태스크.** tasks.csv의 각 행을 `{"task_id", "wbs", "effort", "deps", "percent_complete"}`로
   바꿉니다. 숫자는 float, `deps`는 `;`로 나눈 목록입니다(비어 있으면 `[]`).
3. **프로젝트.** 프로젝트마다 `project_id`, `skill`, `status`, `planned_start`, `planned_finish`,
   `deadline`, `tasks`, 그리고 공수로 가중한 `percent_complete`(Σ 공수 × % ÷ Σ 공수, 소수 첫째 자리
   반올림)를 담은 dict를 만듭니다.
4. **포트폴리오.** `portfolio_id`, `name`, `period`, `found: True`, `projects`를 돌려줍니다. 같은
   형태를 DB에서 만드는 `ma_pmo/connectors/jira_mock.py`와 비교해 보세요.
5. **SPEC.** `SPEC.kind`를 `"tracker"`로 바꿉니다.

## 채점

```bash
ma-pmo learn check 4
```

마지막 항목은 결과를 계획 에이전트의 CPM에 넣어 임계경로가 T-1401 → T-1402 → T-1403인지 확인합니다.

## 생각해 보기

tasks.csv에 projects.csv에 없는 프로젝트가 나오면 어떻게 해야 할까요? PMO가 알아차리게 하려면 어디에
알려야 하고, 왜 에이전트 실행 도중은 아닐까요?
