# Changelog

**English | [한국어](#변경-내역-한국어)**

All notable changes to this project are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses [Semantic Versioning](https://semver.org/).

## [Unreleased]

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

[Unreleased]: https://github.com/ma-pmo/ma-pmo-ext/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/ma-pmo/ma-pmo-ext/releases/tag/v0.1.0

---

## 변경 내역 (한국어)

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
