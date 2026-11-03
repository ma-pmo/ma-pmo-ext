# Changelog

**English | [한국어](#변경-내역-한국어)**

All notable changes to this project are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses [Semantic Versioning](https://semver.org/).

## [Unreleased]

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

[Unreleased]: https://github.com/ma-pmo/ma-pmo-ext/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/ma-pmo/ma-pmo-ext/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/ma-pmo/ma-pmo-ext/releases/tag/v0.1.0

---

## 변경 내역 (한국어)

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
