# 보고서

**[English](REPORTS.md) | 한국어**

보고 단계(A5)가 있는 워크플로는 끝에 보고서를 씁니다. 로드맵 12([#88](https://github.com/ma-pmo/ma-pmo-ext/issues/88))
부터 보고서는 `report.v2`로 저장됩니다. 수치는 MA-PMO가 계산하고, 요약·리스크·조치만 LLM(없으면 규칙)이 씁니다.
API와 CLI로 목록을 보고, 읽고, 내려받을 수 있습니다.

## 종류

PMO는 받는 사람에 따라 다른 보고서를 보냅니다. 종류는 워크플로의 A5 단계에서 정합니다.

| 종류 | 받는 사람 | 구역 |
|---|---|---|
| `status` | 팀과 PMO, 정기(PRINCE2 하이라이트 보고서) | 요약, 핵심 지표, 프로젝트, 허용 범위, 리스크, 조치 |
| `executive` | 스폰서, 한 장 | 요약, 핵심 지표, 예외, 필요한 결정, 조치 |
| `exception` | 운영위원회, 허용 범위를 넘었을 때 | 요약, 예외, 리스크, 조치 |
| `gate` | 단계 게이트, go/no-go 회의 | 요약, 필요한 결정, 리스크, 허용 범위, 조치 |
| `closure` | 프로젝트·단계 종료 | 요약, 프로젝트, 결정, 교훈, 조치 |

기본 워크플로는 이미 종류가 정해져 있습니다.

| 종류 | 워크플로 |
|---|---|
| status | weekly_status, estimation_calibration |
| executive | executive_briefing, quarterly_review, portfolio_prioritization |
| exception | risk_escalation, burndown_alert |
| gate | go_nogo_decision, compliance_audit |
| closure | lessons_learned_closure |

직접 만든 워크플로에서는 이렇게 씁니다.

```json
{"id": "A5", "agent": "A5",
 "params": {"kind": "exception", "audience": "executive", "projects": ["PROJ-31"],
            "as_of": "2026-02-16"}}
```

`audience`(`executive`, `team`)를 빼면 종류의 기본 독자를 따릅니다. `projects`를 주면 포트폴리오 대신 프로젝트
보고서가 되고, `as_of`를 주면 지난 날짜 기준으로 씁니다.

## 계산하는 것

| 수치 | 규칙 |
|---|---|
| 진척 | 트래커의 공수 가중 진척 |
| SPI | 기준일의 획득 가치 ÷ 계획 가치. 계획 가치는 총 공수를 계획 시작일부터 계획 완료일까지 고르게 나눔. 계획 시작 전에는 없음 |
| 예상 완료일 | 계획 시작 + 계획 기간 ÷ SPI(획득 가치 관리의 일반적인 시간 추정) |
| 여유 | 마감 − 예상 완료일. 음수면 늦음 |
| 허용 범위 | SPI가 `MA_PMO_TOLERANCE_SPI`(0.9) 미만이거나, 예상 완료가 마감을 `MA_PMO_TOLERANCE_SLIP_DAYS`(0)일 넘음 |
| 종합 상태 | 가장 나쁜 프로젝트 상태. 허용 범위를 넘으면 최소 amber |
| 변화 | 같은 범위·종류·프로젝트의 직전 보고서 값과 나란히 |
| 리스크, 게이트 결정, 교훈 | 같은 실행에서 A4, A6, A7이 게시한 것(단계가 읽을 수 있을 때. 검토가 기본으로 켜져 있음) |
| 필요한 결정 | 불통과·조건부 게이트, 승인 대기 항목 |

LLM은 이 수치를 받아 그대로 쓰도록 지시받습니다. 문장이 수치와 맞는지 검사하는 일은 로드맵 12의 다음 단계입니다.

## 보기와 내려받기

```bash
ma-pmo report list                                  # 최신순. --kind, --scope
ma-pmo report show latest --kind executive          # 터미널에 Markdown
ma-pmo report export RPT-1a2b3c4d --format html --out report.html
```

| 엔드포인트 | 돌려주는 것 |
|---|---|
| `GET /reports?kind=&scope=&limit=` | 목록, 최신순 |
| `GET /reports/latest?kind=&scope=` | 가장 최근 보고서 |
| `GET /reports/{id}` | 보고서 하나(report.v2 JSON) |
| `GET /reports/{id}/export?format=md\|html\|csv\|json` | 내려받기. `&inline=true`면 HTML을 브라우저에서 엶 |

형식: 위키·메신저용 Markdown, 읽거나 브라우저에서 PDF로 인쇄할 HTML, 스프레드시트용 CSV(프로젝트당 한 행),
다른 도구용 JSON. 보고서는 쓰인 언어로 렌더링됩니다.

## 설정

| 변수 | 기본값 | 뜻 |
|---|---|---|
| `MA_PMO_TOLERANCE_SPI` | 0.9 | 이 SPI 미만이면 허용 범위 밖 |
| `MA_PMO_TOLERANCE_SLIP_DAYS` | 0 | 예상 완료가 마감을 넘어도 되는 일수 |
| `MA_PMO_REPORT_AS_OF` | 오늘 | 이 날짜(YYYY-MM-DD) 기준으로 보고 |

## 한계

- 계획 기준선은 계획 시작일부터 완료일까지의 직선입니다. 시간대별 기준선이 있는 트래커라면 계획 가치가 더
  정확해집니다.
- A2의 CPM 완료일은 태스크마다 한 사람이 하루 8시간 일한다고 가정해서 보고서의 예상 완료일과 다를 수 있습니다.
  보고서는 트래커의 계획 날짜를 씁니다.
- A6 게이트의 "SPI ≥ 0.8" 기준은 시간 기준 SPI가 아니라 공수 가중 완료율을 씁니다.
- 로드맵 12의 다음 단계: 서술을 수치에 묶기, 보고서 간 인사이트, 대시보드 보고서 화면, docx·pdf 내보내기.
