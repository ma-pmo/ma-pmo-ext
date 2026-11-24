# 가드레일과 정책

**[English](GUARDRAILS.md) | 한국어**

로드맵 10([#84](https://github.com/ma-pmo/ma-pmo-ext/issues/84))은 MA-PMO의 여러 점검을 하나의 정책과 하나의 기록
뒤로 모읍니다. 그래서 PMO는 에이전트가 혼자 할 수 있는 범위를 한곳에서 정하고, 무엇을 점검했는지 나중에 보여줄 수 있습니다.

## 가드레일

가드레일은 통제 지점에서 하는 점검입니다. NeMo Guardrails의 레일 종류와 OpenAI Agents SDK의 가드레일을 따랐습니다.

| 지점 | 어디서 |
|---|---|
| `input` | A1에 들어오는 목표나 요청, 웹훅 내용 |
| `retrieval` | 에이전트가 읽는 교훈과 트래커 데이터 |
| `execution` | 커넥터 쓰기, 알림, 플러그인 |
| `output` | 에이전트가 내놓는 결과 |
| `decision` | 커밋 게이트와 승인 |
| `spend` | LLM 호출 |

가드레일은 `allow`(허용), `modify`(수정), `ask`(사람에게 물음), `block`(차단) 중 하나를 이유와 함께 답합니다.
**모드**는 정책에서 정합니다.

- `off`: 돌리지 않습니다.
- `observe`: 돌리고 기록하지만 결과는 `allow`입니다. 켜기 전에 무엇을 막았을지 볼 수 있습니다.
- `enforce`: 답한 대로 적용됩니다.

| 가드레일 | 지점 | 기본값 | 하는 일 |
|---|---|---|---|
| `schema` | output | enforce | 등록된 스키마에 맞지 않는 에이전트 결과를 거부합니다 |
| `budget` | spend | enforce | 한도를 넘은 LLM 호출을 막습니다([COSTS.ko.md](COSTS.ko.md)). 에이전트는 규칙 기반으로 대체합니다 |
| `tolerance` | decision | observe | 결과가 허용 범위를 넘을 것으로 예상되면 예외를 띄웁니다(아래) |

둘 다 로드맵 10 전부터 있던 점검이고, 동작도 그대로입니다. 나중에 추가하는 가드레일은 `observe`로 시작합니다.

## 정책

정책은 워크스페이스마다 버전이 붙는 데이터입니다: `{"guardrails": {이름: {"mode", "params"}}}`.

- `GET /policy`는 지금 적용 중인 정책을 가드레일마다 지점, 모드, 매개변수와 함께 돌려줍니다.
- `PUT /policy` `{guardrails, note}`로 새 버전을 만듭니다. 관리자 역할이 필요합니다.
- `GET /policy/versions`는 모든 버전을 누가 왜 바꿨는지와 함께 보여줍니다.

바꿀 때마다 결정 기록(종류 `policy`)도 남습니다. 실행마다 어느 정책 버전으로 돌았는지 상태(`policy_version`)에 남깁니다.

## 허용 범위

허용 범위는 에이전트가 스스로 어디까지 할 수 있는지 정합니다(PRINCE2의 예외에 의한 관리). 범위 안에서는 에이전트가
결정하고 기록합니다. 에이전트 결과가 범위를 넘을 것으로 **예상**되면, `tolerance` 가드레일이 실제로 넘기 전에 예외를
띄웁니다. 그 메시지는 예측값, 한도, 한도를 정한 단계와 함께 승인 큐로 갑니다. 그 결정의 책임자에게 가며
([역할](REVIEW.ko.md#역할raci)), 승인 알림에도 예외가 담깁니다.

| 차원 | 한도 | 측정 근거 |
|---|---|---|
| 일정 | `max_slip_days` | `schedule.v1`: 예상 완료일과 프로젝트 마감일의 차이 |
| 품질 | `min_spi` | `schedule.v1`: 기준일의 프로젝트 SPI |
| 리스크 | `max_severity` | `risk_alert.v1`: 판정된 심각도 |
| 범위 | `max_unstaffed_pct` | `allocation.v1`: 남은 작업 중 배정되지 않은 시간의 비율 |
| 비용 | `max_cost_overrun_pct` | 아직 측정하지 않습니다. 트래커에 비용 데이터가 없습니다 |
| 편익 | `min_benefit_pct` | 아직 측정하지 않습니다. 트래커에 편익 데이터가 없습니다 |

한도는 워크스페이스, 포트폴리오, 프로젝트마다 `PUT /tolerances` `{tolerances: {workspace, portfolios, projects}, note}`로
정합니다. 관리자 역할이 필요하고, 다른 변경과 마찬가지로 정책 버전이 됩니다. 하위 단계는 상위 단계를 좁히기만 할 수
있습니다. 프로젝트의 `max_slip_days`를 워크스페이스보다 크게 두면 거부됩니다. `GET /tolerances?project=&portfolio=`는
적용 중인 한도와 각 한도가 어느 단계에서 왔는지 보여줍니다.

이 가드레일은 `observe`로 시작합니다. 켜려면 `PUT /policy` `{"guardrails": {"tolerance": {"mode": "enforce"}}}`를
보냅니다. 데모 데이터(2026-02-16 기준)에서 PROJ-31의 지연 허용을 0일로 두면, A2가 7일 지연을 예측해 예외가 뜨고
다른 프로젝트는 범위 안에 머뭅니다.

## 가드레일 기록

결과는 모두 `guardrail.v1` 기록으로 남습니다(`GET /guardrails`, `name`·`point`·`decision`·`outcome`·`run`으로
거르기). 기록 하나에는 다음이 담깁니다.
- 모드
- 점검이 찾은 것(`outcome`)과 실제로 적용된 것(`decision`)
- 이유와 세부 내용(예: 잘못된 필드)
- 정책 버전
- 실행과 메시지

`outcome=block`인데 `decision=allow`이면 observe 모드가 막았을 항목입니다. 이 기록은 소통 기록 안이 아니라 옆에
따로 두므로 알림 개수는 그대로입니다.

데모 데이터에서 기본 시나리오 20개를 돌리면 기록이 약 270개 생깁니다. 결과마다 스키마 점검, LLM 호출 시도마다 예산
점검입니다. 실행 시간이 늘어난 것은 측정되지 않았습니다.
