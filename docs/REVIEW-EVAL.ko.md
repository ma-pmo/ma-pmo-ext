# 검토 평가

**[English](REVIEW-EVAL.md) | 한국어**

검토 체계([REVIEW.ko.md](REVIEW.ko.md))의 각 부분이 무엇을 더하는지 측정했습니다. ArcticSwarm(Yoon et al.,
2026, [arXiv:2609.01870](https://arxiv.org/abs/2609.01870), 표 3)이 검토 단계를 하나씩 걷어 내며 비교한
방식을 따라, 같은 사례를 누적 조건에서 실행했습니다. 재현:

```bash
ma-pmo eval --review
```

## 사례

데모 포트폴리오에 PROJ-22(green, SPI 0.85, 여유 7일, 인력 배정됨)를 바탕으로 만든 프로젝트 PROJ-X를 하나
더하고, 게이트 결정이나 보고서가 다른 에이전트와 어긋나도록(또는 어긋나지 않도록) 바꿨습니다. 라벨은 실행 전에
적어 둔 PMO 규칙과 구성 방식에서 정해집니다.

- red 상태이거나 계획 종료가 마감보다 늦으면 high 리스크
- 아무도 가진 스킬이 없거나 12주 안에 소화할 수 없는 작업량이면 미배정
- 계획의 마지막 주가 마감 주보다 늦으면 지연
- A4가 medium 이상으로 본 프로젝트는 보고서 핵심 리스크에 있어야 함

모든 라벨은 검토자가 돌기 전에 에이전트가 실제로 낸 결과와 대조했습니다.

35 cases: 23 with a conflict (25 gate conflicts, 6 report conflicts), 12 controls. Labels match what the agents produced: yes.

실제 A3, A4, A6, A5, A8을 결정론적 경로(LLM 없음)로 임시 워크스페이스에서 G3 게이트로 실행했습니다.

## 조건

| 조건 | 켜진 것 |
|---|---|
| main | 없음. 모든 단계 격리(0.6.0) |
| +builder | A6·A5가 앞 단계를 읽고 자기 결과를 검토. A5는 빠진 리스크를 추가 |
| +auditor | A8 단계가 모든 결정을 검토 |
| +commit gate | 검토가 통과한 결정만 확정되고 나머지는 사람에게 |
| +alternatives | A8이 이의를 제기한 결정에 대안 제시 |

## 결과

비율은 사례에 대한 95% 부트스트랩 구간(2,000회 재표집, seed 7)과 함께 나타냅니다. 표의 열 이름은 CLI 출력
그대로입니다.

| Condition | Gate conflicts that reached a person | Conflicting gates committed | Report conflicts fixed | Controls held | Approvals added per run | Alternatives per conflict | LLM calls | Median run (ms) |
|---|---|---|---|---|---|---|---|---|
| main | 0% [0, 0] | 100% [100, 100] | 0% [0, 0] | 0% [0, 0] | 0.00 | 0.0 | 0 | 24 |
| +builder | 0% [0, 0] | 100% [100, 100] | 100% [100, 100] | 0% [0, 0] | 0.00 | 0.0 | 0 | 31 |
| +auditor | 0% [0, 0] | 100% [100, 100] | 100% [100, 100] | 0% [0, 0] | 0.00 | 0.0 | 0 | 40 |
| +commit gate | 100% [100, 100] | 0% [0, 0] | 100% [100, 100] | 0% [0, 0] | 0.57 | 0.0 | 0 | 43 |
| +alternatives | 100% [100, 100] | 0% [0, 0] | 100% [100, 100] | 0% [0, 0] | 0.57 | 1.6 | 0 | 44 |

- builder 검토는 A5가 자기 결과를 고칠 수 있어서 보고서 충돌을 모두 해결합니다. 게이트에는 효과가 없습니다.
  A6가 이의를 게시판에 남기지만 아무에게도 묻지 않기 때문입니다.
- 전담 검토(A8)는 모든 결정에 독립적인 판정을 하나 더 남기지만, 여전히 아무에게도 묻지 않습니다.
- **효과를 내는 것은 확정 게이트입니다.**
  - 게이트 충돌이 모두 양쪽 근거와 함께 사람에게 전달됩니다(보류 및 연결).
  - 충돌한 게이트는 하나도 확정되지 않습니다.
  - 대조군은 하나도 보류되지 않습니다.
  - 늘어나는 승인(실행당 0.57건)은 충돌한 채 통과한 게이트(35건 중 20건) 그대로입니다.
- 대안은 충돌당 1.6개가 제시되지만 확정 여부는 바꾸지 않습니다.
- 어떤 조건도 LLM을 호출하지 않으며, 검토 체계는 이 규모의 실행에 20ms 정도를 더합니다.

## 데모 데이터에서의 업무량

데모 포트폴리오에서 기본 시나리오 20개를 검토를 끈 채와 켠 채로 실행했습니다.

| Scenario | Decisions | Held | Newly queued | Already queued | Why | Run ms (off → on) |
|---|---|---|---|---|---|---|
| baseline_planning | 3 | 0 | 0 | 0 | – | 28 → 34 |
| burndown_alert | 1 | 0 | 0 | 0 | – | 25 → 26 |
| capacity_planning | 3 | 0 | 0 | 0 | – | 20 → 31 |
| change_control | 3 | 0 | 0 | 0 | – | 20 → 32 |
| compliance_audit | 4 | 0 | 0 | 0 | – | 14 → 17 |
| estimation_calibration | 1 | 0 | 0 | 0 | – | 19 → 21 |
| estimation_review | 0 | 0 | 0 | 0 | – | 14 → 17 |
| executive_briefing | 1 | 0 | 0 | 0 | – | 26 → 30 |
| go_nogo_decision | 4 | 1 | 0 | 1 | gate.no_open_high_risk | 19 → 28 |
| knowledge_kickoff | 3 | 0 | 0 | 0 | – | 20 → 22 |
| lessons_learned_closure | 4 | 0 | 0 | 0 | – | 17 → 20 |
| new_project_intake | 3 | 0 | 0 | 0 | – | 24 → 34 |
| portfolio_prioritization | 1 | 0 | 0 | 0 | – | 26 → 30 |
| quarterly_review | 1 | 0 | 0 | 0 | – | 22 → 25 |
| resource_conflict | 3 | 1 | 0 | 1 | gate.no_open_high_risk | 21 → 33 |
| risk_escalation | 4 | 1 | 0 | 1 | gate.no_open_high_risk | 20 → 28 |
| risk_rebalance | 3 | 1 | 0 | 1 | gate.no_open_high_risk | 21 → 33 |
| schedule_recovery | 0 | 0 | 0 | 0 | – | 23 → 24 |
| stage_gate_review | 3 | 1 | 0 | 1 | gate.no_open_high_risk | 22 → 29 |
| weekly_status | 1 | 0 | 0 | 0 | – | 15 → 17 |
| **all** | 46 | 5 | 0 | 5 | | |

검토는 데모 데이터에서 **새로 승인을 요청하지 않습니다.** 보류된 결정 5건은 A4가 high로 본 PROJ-31의
게이트로, A6가 이미 승인을 요청했던 것에 이의 내용이 덧붙은 것입니다.

## 결정 (실행 전에 정한 기준)

| 부분 | 기준 | 결과 | 결정 |
|---|---|---|---|
| 확정 게이트 | 전달 ≥ 95%, 대조군 보류 ≤ 5%, 결정론적 경로 추가 비용 없음 | 100%, 0%, LLM 호출 0 | 모든 워크플로에 **기본으로 켬**. `"review": false`로 끌 수 있음 |
| 대안 | 확정 게이트만 있을 때보다 잘못된 확정이 줄어듦 | 0% → 0%(더 줄일 것이 없음) | **기본은 끔**. `MA_PMO_REVIEW_ALTERNATIVES=true`로 켬 |
| LLM 반론 | 위와 같음, 비용 대비 | 실행 안 함: 이 평가에는 LLM 없음 | 만들지 않음 |

## 한계

- 사례는 관찰한 것이 아니라 만든 것입니다. 그래서 검토가 잡도록 설계된 것을 잡고 잡지 말아야 할 것에는
  조용하다는 것을 보여 줄 뿐, 그런 충돌이 얼마나 자주 생기는지는 보여 주지 못합니다. 이는 실제 이슈 트래커
  이력(로드맵 3, [#38](https://github.com/ma-pmo/ma-pmo-ext/issues/38))으로 측정해야 하며, 그때 이 평가를 다시
  실행합니다.
- 라벨 규칙과 검토 규칙이 같은 PMO 규칙에서 나왔습니다. 따라서 일치한다는 것은 게시물이 읽는 쪽에 닿고 판정이
  사람에게 닿는 흐름이 처음부터 끝까지 동작한다는 뜻이지, 규칙 자체가 옳다는 뜻은 아닙니다.
- 모든 것이 결정론적이어서, 구간은 어떤 사례가 표집되었는지만 반영합니다.
- ArcticSwarm의 수치는 개방형 웹 조사의 정확도라서 비교할 수 없습니다. 제거 실험의 형태만 빌렸습니다.
