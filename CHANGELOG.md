# Changelog

**English | [한국어](#변경-내역-한국어)**

All notable changes to this project are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- API authentication middleware ([docs/AUTH.md](docs/AUTH.md)): `MA_PMO_AUTH_MODE=off|api_key|custom` (default `off`), API keys with roles `viewer`, `operator`, `approver`, `admin`, a route policy, a pluggable authenticator for SSO/OIDC or proxy headers, and `GET /auth/whoami`.
- The dashboard sends `NEXT_PUBLIC_API_KEY` as `X-API-Key` when set.
- GitHub and Linear trackers ([docs/INTEGRATIONS.md](docs/INTEGRATIONS.md#github)): `MA_PMO_INTEGRATIONS=github` (`GITHUB_REPOS`, optional `GITHUB_TOKEN`) or `linear` (`LINEAR_API_KEY`, `LINEAR_TEAM_KEYS`). Jira, GitHub and Linear now share one set of project rules (`ma_pmo/integrations/mapping.py`).
- Vector search for A7 ([docs/INTEGRATIONS.md](docs/INTEGRATIONS.md#vector-search-for-lessons-learned-a7)): `MA_PMO_RETRIEVER=vector` with offline character n-gram vectors, or any LiteLLM embedding model via `MA_PMO_EMBEDDING_MODEL`; falls back to lexical search when the model is unreachable. `ma-pmo eval --retrieval` reports recall@k and MRR on 14 labeled English/Korean queries (lexical MRR 0.774 → vector 0.964). Lexical search stays the default.
- Resource calendars for A3 ([docs/INTEGRATIONS.md](docs/INTEGRATIONS.md#resource-calendars-ics)): `MA_PMO_CALENDAR_DIR` with one `<resource_id>.ics` per person; busy hours (Mon–Fri, max 8 h/day, all-day events block the day, free/cancelled ignored) come off weekly capacity before allocation, and utilization is measured against the hours people actually had. Replaces the `NotImplementedError` stub; unchanged results when not configured.
- Confidence calibration of the HITL gate (`ma_pmo/eval/calibration.py`): ECE, Brier score, reliability bins and distinct confidence values from A4 risk alerts (against risk labels) and resolved approvals, plus a threshold what-if table. Shown by `ma-pmo eval`, `GET /eval` (`calibration`) and report section 4. Messages flagged `human_gate_required` count as reviewed at every threshold.
- OpenTelemetry tracing ([infra/otel](infra/otel/README.md)), extra `ma-pmo[otel]`, off unless `OTEL_ENABLED=true`: one trace per scenario run (`invoke_workflow` → `invoke_agent` → `chat`) with GenAI semantic-convention attributes, failed LLM calls recorded as errors, and deterministic fallbacks marked (`ma_pmo.fallback`). Jaeger compose file for local viewing.
- MCP server ([docs/MCP.md](docs/MCP.md)): `ma-pmo mcp` (stdio, extra `ma-pmo[mcp]`) with eight tools — portfolio status, CPM schedule, risks, pending approvals, scenarios, scenario runs, H1–H5 verdicts, lessons learned. Approving is not a tool.

### Changed
- Dashboard: Evaluation shows confidence calibration (with the threshold table) and A7 search quality; Integrations shows platform status (auth, tracing, search, calendars, MCP) and the real environment variable names to set; the top bar warns when API auth is off. New endpoints `GET /system` and `GET /eval/retrieval`. README screenshots and demo GIF updated.
- `GET /eval` populates KPIs only on an empty database by default, so opening the Evaluation page no longer queues a new approval each time.

### Security
- With auth on, the approver recorded on a HITL decision is the authenticated user; the `approver` in the request body is ignored.

## [0.3.0] - 2026-11-05

### Added
- Course "Learn harness engineering with MA-PMO" ([docs/learn](docs/learn/README.md)): seven lectures in English and Korean, four labs (notifier plugin, dataset repair, ablation experiment, custom tracker) with starter files, reference solutions and automatic checks.
- `ma-pmo learn list | scenarios | start N | check N` (`--solution` to copy or check the reference solution).
- CI test that every lab solution passes and every untouched starter fails.
- `AGENTS.md`: repository conventions for contributors and AI coding tools.

## [0.2.0] - 2026-11-04

### Added
- Pluggable integrations (`ma_pmo/integrations/`): Slack and generic webhook notifiers, a Jira Cloud tracker, and a `ma_pmo.integrations` entry-point group for third-party plugins. Enabled with `MA_PMO_INTEGRATIONS`; see [docs/INTEGRATIONS.md](docs/INTEGRATIONS.md).
- Integration events: `approval.requested`, `approval.resolved`, `risk.detected`, `gate.failed`, `report.generated`.
- `GET /integrations` and `POST /integrations/{name}/test`.
- Smoke and regression test suites (`make test-smoke`, `make test-regression`), run as separate CI steps.

- Evaluation template generator:
  - data template: `ma-pmo template data` writes fill-in CSV/JSON files with a bilingual guide; `ma-pmo template validate` checks them line by line; `ma-pmo eval --data` runs H1–H5 on them in an isolated database.
  - report template: `ma-pmo template report --format md|html` and `GET /eval/report` turn H1–H5 results into a report with verdicts, KPIs and limitations (English/Korean).
  - experiment template: `ma-pmo harness new` scaffolds an experiment and its test; experiments are discovered automatically.
  - `GET /templates/data.zip`, `POST /templates/validate`; `GET /eval` now includes a verdict summary.

- Admin-style dashboard: grouped sidebar navigation with a pending-approvals badge, top bar with API status and language switch, mobile menu, light/dark themes, and new **Evaluation** (verdicts, report, data template download and validation) and **Integrations** (status, test send) pages.

### Security
- `POST /templates/validate` builds extraction paths from known template file names only, never from archive entry names.

### Changed
- Agents, the API and the evaluation harness read portfolio data from the configured tracker (falls back to the demo data).
- Dashboard, Scenarios (category tabs) and Approvals (table with inline actions) rebuilt on shared admin components; README screenshots and demo GIF updated.
- Releases are published from the GitHub Releases page; the workflow then uploads to PyPI and attaches the build files.

## [0.1.0] - 2026-10-29

First public release.

### Added
- Seven operational agents: A1 Orchestrator, A2 Planning (CPM), A3 Resources, A4 Risk, A5 Reporting, A6 Governance (stage gates G1–G4), A7 Knowledge (RAG with mandatory citations).
- Offline operation: deterministic fallbacks for every LLM step, so the full pipeline runs without an API key. LLM path through LiteLLM (Anthropic or local Ollama).
- Structured `.v1` message protocol with an append-only audit log and a human-in-the-loop approval queue.
- Five-axis KPI telemetry (time, resource, delivery, risk, cost), an H1–H5 evaluation harness and an experiment harness with ablations.
- 20 lifecycle scenarios with a four-phase trace (plan → execute → complete → insight) and paper-ready Markdown export.
- English/Korean support across the dashboard (language toggle), API responses (`?lang=`, `Accept-Language`), reports and LLM output (`MA_PMO_LANG`). Lessons-learned corpus in both languages.
- Next.js dashboard with KPIs, charts, scenarios and the approval queue.
- `ma-pmo` command-line tool (`init-db`, `serve`, `eval`, `harness`) and PyPI packaging.
- Docker Compose and Kubernetes manifests.
- Dual licensing (AGPL-3.0-or-later + commercial), trademark policy, citation metadata and community files.

### Changed
- Python modules now live in the `ma_pmo` package (`ma_pmo.core`, `ma_pmo.agents`, …) instead of top-level packages.
- Gate IDs are now `G1-initiation`, `G2-planning`, `G3-execution`, `G4-closure`. The previous Korean IDs are still accepted.

### Fixed
- Progress bars on the dashboard did not render their fill.

[Unreleased]: https://github.com/ma-pmo/ma-pmo-ext/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/ma-pmo/ma-pmo-ext/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/ma-pmo/ma-pmo-ext/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/ma-pmo/ma-pmo-ext/releases/tag/v0.1.0

---

## 변경 내역 (한국어)

### [Unreleased]

- API 인증 미들웨어([docs/AUTH.ko.md](docs/AUTH.ko.md)): `MA_PMO_AUTH_MODE=off|api_key|custom`(기본 `off`), 역할(`viewer`, `operator`, `approver`, `admin`)이 있는 API 키, 경로별 권한 정책, SSO/OIDC·프록시 헤더용 인증기 플러그인, `GET /auth/whoami`.
- 대시보드는 `NEXT_PUBLIC_API_KEY`가 있으면 `X-API-Key`로 보냅니다.
- GitHub·Linear 트래커([docs/INTEGRATIONS.ko.md](docs/INTEGRATIONS.ko.md)): `MA_PMO_INTEGRATIONS=github`(`GITHUB_REPOS`, 선택 `GITHUB_TOKEN`) 또는 `linear`(`LINEAR_API_KEY`, `LINEAR_TEAM_KEYS`). Jira·GitHub·Linear가 같은 프로젝트 규칙(`ma_pmo/integrations/mapping.py`)을 공유.
- A7 벡터 검색([docs/INTEGRATIONS.ko.md](docs/INTEGRATIONS.ko.md)): `MA_PMO_RETRIEVER=vector`(오프라인 문자 n-gram 벡터) 또는 `MA_PMO_EMBEDDING_MODEL`로 LiteLLM 임베딩 모델 사용, 모델에 연결할 수 없으면 어휘 검색으로 대체. `ma-pmo eval --retrieval`로 영어·한국어 라벨 질의 14개의 recall@k·MRR 측정(어휘 MRR 0.774 → 벡터 0.964). 기본값은 어휘 검색 유지.
- A3용 자원 캘린더([docs/INTEGRATIONS.ko.md](docs/INTEGRATIONS.ko.md)): `MA_PMO_CALENDAR_DIR`에 사람별 `<resource_id>.ics`를 두면 바쁜 시간(월~금, 하루 최대 8시간, 종일 일정은 하루 전체, 한가함·취소 일정 제외)을 주간 가용 시간에서 빼고 배정하며, 활용률도 실제 가용 시간 기준으로 계산. 기존 미구현 스텁 대체, 설정하지 않으면 결과 동일.
- HITL 게이트의 확신도 보정 측정(`ma_pmo/eval/calibration.py`): A4 리스크 경보(레이블 대비)와 처리된 승인으로 ECE, Brier 점수, 구간별 신뢰도, 확신도 값 종류를 계산하고, 기준값별 검토 대상과 빠져나간 오류를 표로 보여 줌. `ma-pmo eval`, `GET /eval`(`calibration`), 보고서 4절.
- OpenTelemetry 추적([infra/otel](infra/otel/README.md)), extra `ma-pmo[otel]`, `OTEL_ENABLED=true`일 때만 동작: 시나리오 실행마다 트레이스 하나(`invoke_workflow` → `invoke_agent` → `chat`), GenAI 시맨틱 규약 속성, 실패한 LLM 호출은 오류로, 대체 경로 사용은 `ma_pmo.fallback`으로 표시. 로컬 확인용 Jaeger compose 파일.
- MCP 서버([docs/MCP.ko.md](docs/MCP.ko.md)): `ma-pmo mcp`(stdio, extra `ma-pmo[mcp]`)로 포트폴리오 현황, CPM 일정, 리스크, 승인 대기, 시나리오 목록·실행, H1~H5 판정, 과거 교훈 도구 8개 제공. 승인은 도구로 제공하지 않음.
- 대시보드: 평가 화면에 확신도 보정(기준값 표 포함)과 A7 검색 품질, 연동 화면에 플랫폼 상태(인증·추적·검색·캘린더·MCP)와 실제로 넣을 환경 변수 이름, 상단 바에 인증 꺼짐 경고. 새 API `GET /system`, `GET /eval/retrieval`. README 스크린샷과 데모 GIF 갱신.
- `GET /eval`은 기본적으로 빈 데이터베이스일 때만 KPI를 채우므로, 평가 화면을 열 때마다 승인 대기가 새로 생기지 않음.
- 보안: 인증이 켜져 있으면 HITL 승인 기록에는 인증된 사용자가 남고, 요청 본문의 `approver`는 무시됩니다.

### [0.3.0] - 2026-11-05

- 교육 과정 "MA-PMO로 배우는 하네스 엔지니어링"([docs/learn](docs/learn/README.ko.md)): 영어·한국어 강의 7개, 실습 4개(알림 플러그인, 데이터 고치기, 제거 실험, 나만의 트래커)와 시작 코드·정답·자동 채점.
- `ma-pmo learn list | scenarios | start N | check N` 명령(`--solution`으로 정답 복사·채점).
- 모든 실습 정답은 통과하고 손대지 않은 시작 코드는 실패하는지 CI에서 검사.
- `AGENTS.md`: 기여자와 AI 코딩 도구를 위한 저장소 규칙.

### [0.2.0] - 2026-11-04

- 보안: 평가 양식 업로드(`POST /templates/validate`)가 zip 안 경로를 저장 경로에 쓰지 않도록 수정.
- 플러그인 연동 추가: Slack·범용 웹훅 알림, Jira Cloud 데이터 연결, 외부 패키지용 `ma_pmo.integrations` entry point. `MA_PMO_INTEGRATIONS`로 켭니다([docs/INTEGRATIONS.ko.md](docs/INTEGRATIONS.ko.md)).
- 연동 이벤트: 승인 요청·승인 처리·고위험 리스크·게이트 미통과·보고서 생성.
- `GET /integrations`, `POST /integrations/{name}/test` API.
- smoke·regression 테스트(`make test-smoke`, `make test-regression`)를 CI에서 단계별로 실행.
- 에이전트·API·평가 하네스가 설정된 데이터 연동을 사용(없으면 데모 데이터).
- 관리자 스타일 대시보드: 그룹형 사이드바(승인 대기 배지), API 상태·언어 전환 상단 바, 모바일 메뉴, 라이트/다크 테마, 새 **평가**(판정·보고서·데이터 양식 다운로드/검사)와 **연동**(상태·테스트 전송) 화면.
- 평가 템플릿 생성기: 조직 데이터 입력 양식(`ma-pmo template data`)·검사(`validate`)·실데이터 평가(`ma-pmo eval --data`), 판정이 담긴 평가 보고서(`ma-pmo template report`, `GET /eval/report`), 실험 뼈대 생성(`ma-pmo harness new`).

### [0.1.0] - 2026-10-29

첫 공개 릴리스.

#### 추가
- 7개 실동작 에이전트: A1 오케스트레이터, A2 계획(CPM), A3 자원, A4 리스크, A5 보고, A6 거버넌스(스테이지 게이트 G1~G4), A7 지식(출처 인용 강제 RAG).
- 오프라인 동작: 모든 LLM 단계에 결정론적 폴백이 있어 API 키 없이 전체 파이프라인 동작. LiteLLM 경유 LLM 경로(Anthropic 또는 로컬 Ollama).
- 구조화 `.v1` 메시지 프로토콜, append-only 감사 로그, Human-in-the-loop 승인 큐.
- 5축 KPI 텔레메트리(시간·자원·전달·리스크·비용), H1~H5 검증 하네스, ablation 지원 실험 하네스.
- 20개 생애주기 시나리오(계획 → 수행 → 완료 → 인사이트)와 논문용 Markdown 내보내기.
- 영어/한국어 지원: 대시보드(언어 토글), API 응답(`?lang=`, `Accept-Language`), 보고서·LLM 출력(`MA_PMO_LANG`). 교훈 코퍼스도 두 언어로 제공.
- KPI·차트·시나리오·승인 큐를 갖춘 Next.js 대시보드.
- `ma-pmo` CLI(`init-db`, `serve`, `eval`, `harness`)와 PyPI 패키징.
- Docker Compose·Kubernetes 매니페스트.
- 듀얼 라이선스(AGPL-3.0-or-later + 상업용), 상표 정책, 인용 메타데이터, 커뮤니티 문서.

#### 변경
- Python 모듈을 최상위 패키지 대신 `ma_pmo` 패키지(`ma_pmo.core`, `ma_pmo.agents` 등) 아래로 이동.
- 게이트 ID를 `G1-initiation`, `G2-planning`, `G3-execution`, `G4-closure`로 변경. 기존 한글 ID도 계속 인식.

#### 수정
- 대시보드 진척률 막대가 채워지지 않던 문제.
