# MA-PMO로 배우는 하네스 엔지니어링

**[English](README.md) | 한국어**

**조직에서 믿고 돌릴 수 있고, 측정 가능하고, 안전한** 멀티 에이전트 시스템을 만드는 실습 과정입니다.
에이전트 시스템에서 모델은 일부일 뿐입니다. 나머지, 즉 에이전트 사이의 계약, 대체 경로(fallback),
승인 게이트, 측정, 실험, 외부 연동이 *하네스(harness)*입니다. 이 과정은 그 하네스를 실제로 동작하는
시스템 위에서 가르칩니다. PMO 업무를 맡는 7개 에이전트, MA-PMO입니다.

모든 강의는 이 저장소의 실제 코드를 가리킵니다. 모든 실습에는 시작 코드, 정답, 자동 채점이 있어서
강사 없이도 피드백을 받을 수 있습니다. API 키는 필요 없습니다. 전부 오프라인으로 돌아갑니다.

## 대상

Python을 읽을 수 있고 "LLM 데모"에서 "PMO가 믿을 수 있는 에이전트 시스템"으로 넘어가고 싶은 개발자.
이런 시스템에 무엇을 요구해야 하는지 알고 싶은 프로젝트 관리자는 1, 4, 5강이 가장 도움이 됩니다.

## 준비 (5분)

```bash
pip install ma-pmo          # 저장소를 clone했다면: make dev
ma-pmo init-db              # 데모 포트폴리오 + 교훈 데이터
ma-pmo learn list           # 실습 6개
```

실습은 `./learn/labN`에 복사되고 `ma-pmo learn check N`으로 채점합니다. 실습은 여러분의 실제
데이터베이스를 건드리지 않습니다. 실습 3은 별도 SQLite 파일을 씁니다.

## 과정 지도

| # | 강의 | 배우는 것 | 실습 |
|---|---|---|---|
| 1 | [에이전트는 왜 실패하나, 하네스란 무엇인가](01-why-harness.ko.md) | 하네스가 잡아내야 할 실패 유형 | — |
| 2 | [계약으로서의 구조화 메시지](02-structured-messages.ko.md) | 스키마, 버전, 추가 전용 감사 로그 | — |
| 3 | [결정론적 대체 경로: 오프라인 우선](03-offline-fallbacks.ko.md) | LLM 없이도 모든 LLM 단계가 동작하게 하기 | — |
| 4 | [사람 승인 게이트(HITL)](04-human-in-the-loop.ko.md) | 어떤 결정을 사람이 승인해야 하고, 어떻게 하는가 | — |
| 5 | [에이전트 측정하기](05-measuring-agents.ko.md) | KPI, 가설, 기준선, 정답 레이블 | [실습 2](../../ma_pmo/learn/labs/lab2_dataset/README.ko.md): 데이터 고치기 |
| 6 | [실험, 제거 실험, 테스트](06-experiments.ko.md) | 주장을 재현 가능한 실행으로 바꾸기 | [실습 3](../../ma_pmo/learn/labs/lab3_ablation/README.ko.md): 제거 실험 |
| 7 | [연동과 장애 격리](07-integrations.ko.md) | 실패해도 에이전트를 멈추지 않는 플러그인 | [실습 1](../../ma_pmo/learn/labs/lab1_notifier/README.ko.md): 알림 · [실습 4](../../ma_pmo/learn/labs/lab4_tracker/README.ko.md): 트래커 · [실습 5](../../ma_pmo/learn/labs/lab5_mcp_tool/README.ko.md): MCP 도구 |
| 8 | [에이전트 운영하기: 신원, 추적, 보정](08-operating-agents.ko.md) | 누가 무엇을 했는지, 실행이 왜 그렇게 됐는지, 게이트가 위험을 거르는지 | [실습 6](../../ma_pmo/learn/labs/lab6_calibration/README.ko.md): 게이트 보정 |

권장 순서: 1~4강 → 7강과 실습 1(가장 쉬움) → 5강과 실습 2 → 6강과 실습 3 → 실습 4 → 실습 5(`pip install "ma-pmo[mcp]"` 필요) → 마지막으로 8강과 실습 6.
강의는 각 1시간, 실습은 각 1~2시간 정도로 잡으세요.

## 실습 진행 방법

```bash
ma-pmo learn start 1              # 시작 코드를 ./learn/lab1에 복사
# learn/lab1/README.ko.md를 보며 learn/lab1/file_notifier.py 수정
ma-pmo learn check 1              # 요구사항마다 ✓/✗, ✗에는 힌트
ma-pmo learn start 1 --solution   # 막히면 정답을 ./learn/lab1-solution에 받기
```

강사용: `ma-pmo learn check N --solution`으로 정답이 통과하는지 확인할 수 있습니다. 저장소 CI는
모든 정답이 통과하고, 손대지 않은 시작 코드는 모두 실패하는지 검사합니다.

## 출처

강의 + 실습 형식은 [walkinglabs/learn-harness-engineering](https://github.com/walkinglabs/learn-harness-engineering)
(MIT 라이선스)에서 착안했습니다. 이곳의 강의, 실습, 코드는 MA-PMO에 맞춰 새로 작성한 것입니다.
