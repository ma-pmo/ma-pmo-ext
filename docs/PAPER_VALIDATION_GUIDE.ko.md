# 논문 유효성 검증 & 스크린샷 가이드

**[English](PAPER_VALIDATION_GUIDE.md) | 한국어**

> 영문 문서가 기준이며, 이 문서는 한국어 번역본입니다.


MA-PMO 구현으로 논문의 개념 아키텍처·가설(H1~H5)을 **실행 가능한 시스템**에서 실증하고,
논문 그림(Figure)으로 캡처하기 위한 절차서.

> 핵심 메시지: 논문 §4 시뮬레이션(규칙 로직)을 **실제 멀티 에이전트 시스템**으로 대체하고,
> 5축 KPI를 **실측 텔레메트리**로 수집하여 H1~H5를 검증한다. 대부분 API 키 없이 재현 가능.

---

## 0. 사전 준비 (5분)

```bash
cd ma-pmo
make dev                 # 의존성 설치 + .env 생성
make db-init             # SQLite 스키마 + 픽스처(포트폴리오·교훈) 로드
make test                # 전체 테스트 통과 확인 (검증의 재현성 근거)
```

두 서버 기동 (터미널 2개):
```bash
make api                 # http://localhost:8000  (API, /docs 스웨거)
make web                 # http://localhost:3000  (대시보드)
```

> LLM 경로(A4·A5·A7 종합·A1 라우팅)까지 캡처하려면 `.env`에 `ANTHROPIC_API_KEY` 설정 후 `make api` 재기동.
> 키가 없으면 결정론적 폴백으로 동작하며, **비용축(토큰)만 미측정**이고 나머지는 그대로 재현된다(RCT는 폴백 보고 기준으로 측정).
> 한국어 결과를 원하면 대시보드에서 `한국어`를 선택하거나 API에 `?lang=ko`를 붙인다(`MA_PMO_LANG=ko`로 기본값 변경 가능).

---

## 1. 시나리오 ↔ 가설 매핑 (핵심 그림 소스)

`시나리오` 탭에서 유즈케이스를 선택하면 **계획 → 수행 → 완료 → 인사이트** 4단계가 실행되고,
각 인사이트가 가설로 매핑된다. 논문 "결과/검증" 절의 대표 그림으로 사용.

조직 프로젝트 생애주기 전반을 다루는 **20개 시나리오**(5개 카테고리)를 제공한다.
전체 목록: `GET /scenarios`. 대표 시나리오:

| 카테고리 | 대표 시나리오 | 협업 | 검증 가설 |
|---|---|---|---|
| 착수 | 지식기반 착수 계획 / 신규 프로젝트 인테이크·타당성 / 기준선 수립 / 견적 검증 | A7·A2·A3·A6 | H4, H5, H2 |
| 실행 | 분기 통합 리뷰 / 주간 상태보고 / 리스크→자원 재배분 / 일정 회복 / 자원 경합 / 리스크 에스컬레이션 / 번다운 대응 | A2·A3·A4·A5·A6 | H1, H2, H3 |
| 거버넌스 | 스테이지 게이트 심사 / 변경 통제 / 방법론 준수 감사 / Go-NoGo 의사결정 | A2·A4·A6·A5 | H3, H5, H1 |
| 지식·종료 | 종료·교훈 정리 / 견적 캘리브레이션 | A6·A7·A5·A2 | H4, H1 |
| 포트폴리오 | 우선순위·자원 최적화 / 경영진 통합 브리핑 / 용량 계획 | A2·A3·A4·A5·A6 | H1, H2, H3, H5 |

각 시나리오는 계획→수행→완료→인사이트 4단계로 실행되며 인사이트가 위 가설로 자동 매핑된다.

---

## 2. 그림별 캡처 절차

### Figure A — 시스템 아키텍처 (감독자–작업자)
- 소스: `README.md`(영문) · `README.ko.md`(한글) 아키텍처 다이어그램 + `ma_pmo/core/graph.py`
- 캡처: `http://localhost:8000/docs` (엔드포인트 = 기능 매핑) 스크린샷

### Figure B — 에이전트 협업 4단계 (대표 그림)
- 화면: `시나리오` 탭 → "분기 포트폴리오 통합 리뷰" 실행
- 캡처: 계획(A1 위임) → 수행(A2/A4/A5 산출·소요시간) → 완료(종합) → 인사이트(H1/H3) 전체 타임라인
- 논문 메시지: *구조화 메시지 기반 협업 + 단계별 계측*

### Figure C — 5축 KPI 대시보드
- 화면: `대시보드` 탭
- 준비: "일정 산출(A2)", "자원 배분(A3)", "게이트 리뷰(A6)" 버튼 클릭 → KPI 채움
- 캡처: RCT·활용률/유휴율(H2)·SPI·슬리피지·RLT 카드 + 프로젝트 상태 + 리스크 등록부

### Figure D — HITL 거버넌스 게이트
- 화면: `승인 큐 (HITL)` 탭
- 준비: `curl -X POST localhost:8000/demo/gated-message` (또는 A6 conditional 게이트)
- 캡처: 대기 승인 항목(발신 에이전트·confidence·payload) + 승인/반려 버튼
- 논문 메시지: *고위험 결정의 인간 승인 게이트(§8 거버넌스)*

### Figure B-2 — 에이전트 행위 감사 로그 (구조화 통신 §4)
- 화면: `시나리오` 실행 결과 하단 "에이전트 간 구조화 메시지 (감사 로그)" 표
- 또는 API: `GET /messages?task_ref=PORTFOLIO#2026-Q1`
- 캡처: 발신→수신·intent·schema·confidence·HITL 열 (누가 누구에게 무엇을 보냈는지)
- 논문 메시지: *자유대화 대신 스키마 메시지 + append-only 감사 추적으로 재현성 확보*
- 콘솔 실시간 로그(행위): `make api` 서버 stdout 에 `message`/`kpi`/`execute_*` 이벤트 출력

### 논문용 결과 자동 추출 (Markdown)
- UI: 시나리오 실행 후 "📄 논문용 결과 보기" → Markdown 복사
- API: `POST /scenarios/{id}/run?format=markdown` → `paper_markdown` 필드
- 산출: 협업 단계표 + 5축 KPI 실측표 + 가설 검증 + 감사추적 메시지표 (논문에 그대로 삽입)
- 저장된 예시: `docs/evidence_*.ko.json`(한국어) · `docs/evidence_*.json`(영어) (`paper_markdown` 키)

### Figure E — 가설 H1~H5 실증 결과 (정량 근거)
- 명령:
  ```bash
  ma-pmo eval                  # 콘솔 표 (= python -m ma_pmo.eval.run)
  curl 'localhost:8000/eval?lang=ko'   # JSON (precision/recall/F1 등)
  ```
- 캡처: H3 precision/recall/F1, H2 활용률/유휴율, H4 A7 ablation, H5 복잡성 층화
- 논문 표: 아래 §3 표를 그대로 사용

---

## 3. 가설 검증 결과 표 (예시 — 픽스처 기준)

`GET /eval` 산출을 논문 표로 정리. **실데이터 도입 시 이 표가 실측치로 대체된다.**

| 가설 | 지표 | 측정값(픽스처) | baseline/정답 | 판정 |
|---|---|---|---|---|
| H1 보고시간 | RCT(초) | LLM 시 측정 | 수작업 21,600s | 단축율 계산 |
| H2 유휴율 | 활용률/유휴율 | 45.1% / 54.9% | 목표 80% | 재배분 여지 식별 |
| H3 리스크 | precision/recall/F1 | **1.0 / 1.0 / 1.0** | ground-truth 레이블 | 규칙기반 탐지 유효 |
| H4 성공률 | 지식 citation | A7 on=2 / off=0 | ablation | 근거 확보 기여 |
| H5 조절 | 복잡성별 SPI | low 0.523 / high 0.54 | 복잡성 중앙값 | 층화 분석 |

> H3의 규칙기반 baseline은 `ma_pmo/agents/risk_signals.py`, 정답 레이블은 `ma_pmo/fixtures/risk_ground_truth.json`.
> LLM 에이전트와의 비교(H3 규칙 vs LLM)는 A4 실행 시 `kpi_event.meta.agreement`에 기록된다.

---

## 4. 추적성 (논문 ↔ 코드)

| 논문 | 구현 |
|---|---|
| §3.2 에이전트 표 | `ma_pmo/agents/*.py` (A1~A7) |
| §3.3 구조화 메시지 | `ma_pmo/core/schemas/`, `ma_pmo/core/protocol.py`, `agent_message`(append-only) |
| §3.5 5축 지표 | `ma_pmo/core/kpi.py`, `kpi_event` 테이블 |
| §4 시뮬레이션→실측 | 에이전트 실동작 + `ma_pmo/eval/harness.py` |
| 가설 H1~H5 | `ma_pmo/eval/harness.py`, `GET /eval`, `시나리오` 탭 |
| §8 HITL 거버넌스 | `ma_pmo/core/hitl.py`, 승인 큐, A6 게이트 |

---

## 5. 원클릭 재현 스크립트

```bash
# 모든 에이전트 구동 + KPI 채움 + 가설 산출 (API 키 없이)
make db-init
ma-pmo eval
# 시나리오 3종 실행 결과 저장 (한국어)
for s in quarterly_review risk_rebalance knowledge_kickoff; do
  curl -s -X POST "localhost:8000/scenarios/$s/run?format=markdown&lang=ko" > docs/evidence_$s.ko.json
done
```

산출물(`docs/evidence_*.json`, `GET /eval` JSON)은 논문 부록의 원자료로 첨부 가능하다.

---

## 6. 한계와 유효성 위협 (논문 Limitations 절 초안)

- **데이터**: 현재는 픽스처 기반. 실 프로젝트 로그로 baseline·ground-truth 교체 필요(→ H1~H5 통계검정).
- **표본**: 포트폴리오 1개·프로젝트 3개로 precision/recall 표본이 작음(대규모 데이터 필요).
- **LLM 비결정성**: A4·A5·A7 종합은 LLM 의존 → 재현성 위해 결정론적 폴백·스키마 검증·구조화 출력으로 완화.
- **외부 타당도**: mock 커넥터 → 실제 Jira/Calendar/ERP 연동 및 현장 파일럿으로 확장 필요(P5).
