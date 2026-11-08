# Changelog

**English | [한국어](#변경-내역-한국어)**

All notable changes to this project are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.6.0] - 2026-11-08

### Changed
- README screenshots and demo GIF cover the new Workflows and Costs pages; `docs/capture_seed.py` makes the sample spend, budgets and recommendations they show, without calling any provider.
- A principal with no roles can no longer read: a custom authenticator that returned `Principal(subject)` without roles had read access to everything, and now has none unless it has a membership.

### Fixed
- The dashboard showed run, version and approval times as if UTC were local time (nine hours early in Asia/Seoul), in the browser's date format rather than the UI language's. Times are now read as UTC and shown in local time in the UI language.
- On phones the top bar was crowded: the page name now shortens when space runs out and the API status keeps its dot (the text stays for screen readers and as a tooltip).
- Dry runs threw away the LLM spend of their throwaway workspace and ignored budgets. Their spend is now kept in the workspace's ledger (`purpose: dry_run`) and the workspace's budgets apply.
- Allocating one portfolio erased every portfolio's plan. A3 now replaces only its own, and an unknown scope erases nothing.
- A person shared by two portfolios could be booked twice: hours planned elsewhere now count as busy.
- Allocation always started at 2026-W03 and could not cross a year. A portfolio can set `plan_start` (ISO week, also an optional `portfolio.csv` column); otherwise it starts from the current week. The sample portfolio keeps 2026-W03.

### Added
- Replay evaluator and model recommendations (Roadmap 6 complete, migration `0011_recommendations`): replay a workflow step on the fast model against the demo data, `N` runs a side, and compare step cost, valid-output rate and (for risk steps) risk accuracy with 95% bootstrap intervals; the verdict is recommended, not recommended or inconclusive. An approver's approval saves a draft with the change; nothing is published by itself. `ma-pmo replay`, `ma-pmo recommendation`, `/recommendations`, and a section on the Costs page.
- Per-step model routing: a workflow step with `"model_tier": "fast"` uses `LLM_MODEL_FAST` (until now configured but never used); everything else stays on `LLM_MODEL`. Chosen in the workflow editor's Model column, shown in the step table and graph; the ledger shows the effect by model. On Anthropic models the system prompt is marked cacheable (`LLM_PROMPT_CACHE`, on by default).
- Budgets (migration `0010_budgets`): a monthly and a per-run budget per workspace, each with a warning and a hard limit in USD. Past a warning people are told once (`budget.warning` event); past a hard limit agents stop calling the LLM and use their deterministic fallbacks, so the run still succeeds, and it is marked (`budget_fallback` on runs and results, a badge on the workflow view, a list on the Costs page). Set them on the Costs page, with `ma-pmo budget`, or `PUT /budgets/{month|run}` (admin).
- Cost ledger (Roadmap 6, migration `0009_llm_calls`): every LLM call is recorded with its run, step, agent, model, tokens (cache reads and writes kept apart) and USD, priced from a versioned table: your own (`MA_PMO_PRICE_TABLE`) or the one bundled with the pinned LiteLLM. An unknown price stays null and is counted as unpriced, never guessed. A **Costs** page and `GET /costs?by=model|agent|workflow|run|day` show it; `GET /runs/{id}/costs` per step. See [docs/COSTS.md](docs/COSTS.md).
- Workflow editor (Roadmap 5 complete): **Edit** on the workflow page opens a form to add, remove and reorder steps, choose what each waits for and set parameters, checked by the server's validator as you type with a live graph; required steps of the version in use are locked. **Dry run on demo data** (`POST /workflows/dry-run`) runs the draft in a throwaway workspace on the sample portfolio and erases it: no real data, approval or notification is touched, and trackers read the demo data even when Jira, GitHub or Linear is configured. Save a draft, then publish it from the Versions table. Phones stay read-only.
- Workflow versions (migration `0008_workflow_versions`, row-level security like the other tables): save a workflow as an immutable **draft**, then an `approver` or `admin` **publishes** it and it runs in that workspace. Every version stays readable (a Versions table on the workflow page, `GET /workflows/{id}/versions[/{v}]`), and each run records the version it used (`workflow_version` in `GET /runs`, shown in the run menu). One validator for the API (`POST /workflows/validate`, 422 with `detail.problems`), the CLI (`ma-pmo workflow validate | draft | versions | publish`) and the dashboard: unknown agents or categories, a gate step that is not required, and removing or changing a required step are rejected; publishing checks again. `/scenarios`, scenario runs and the MCP tool use the version in use.
- Live run overlay on the workflow view: pick a run (or **See it on the workflow** from a scenario trace) to colour each step done, running, awaiting approval, failed or not started, with errors and retries in the table; it refreshes every two seconds while the run is going. The graph is the workflow exactly as that run saved it, marked when it differs from today's. `GET /runs/{id}/workflow` returns it; `GET /runs` takes `workflow`.
- Workflow view (Roadmap 5, read-only): a **Workflows** page draws each workflow as stages that can run in parallel, with arrows to the steps that wait, required steps (gates) marked, the same steps as a table, keyboard focus on every step, and a menu instead of the list on phones. `GET /workflows` lists built-in and your own workflows (and files that failed to load); `GET /workflows/{id}` returns each step's resolved `needs` and `level`. No graph library is added.
- Dashboard workspace and portfolio switcher (sidebar). It lists only what the caller can enter, remembers the choice, and sends `X-Workspace` with every request; the dashboard's portfolio status, risks, allocations, plan, gate review and goals follow the chosen portfolio. New `GET /workspaces` (the caller's workspaces and roles there, no `X-Workspace` needed) and `GET /portfolios`; `GET /risks` takes `scope`.
- Postgres row-level security (migration `0007_row_level_security`): the database itself keeps workspaces apart, behind the API's filter. Each transaction tells Postgres its workspace; rows of other workspaces are invisible and cannot be written. It applies only to ordinary roles, so the compose file and Kubernetes manifests now run Postgres with a `postgres` admin and create `mapmo` as an ordinary role that owns the database ([deploy/README.md](deploy/README.md#postgres-roles), including how to move an existing database). CI runs the Postgres suite as such a role and runs the API image on the compose Postgres.
- Workspace memberships: what a caller may do is decided per workspace. A key role written `workspace/role` applies only there, and `ma-pmo workspace create | list | members | grant | revoke` keeps memberships in the database (migration `0006_memberships`). A caller with no role in a workspace gets the same 404 as for one that does not exist. Plain roles still apply everywhere, so existing keys keep working. `GET /auth/whoami` adds `workspace`.
- Workspace isolation: a request runs in the workspace named by `X-Workspace` (CLI, MCP and background work use `MA_PMO_WORKSPACE`), and every ORM query, join and subquery is filtered by it automatically; new rows land in it. Ids from another workspace are not found (`POST /approvals/{id}` now answers 404 for an unknown approval instead of 400). A test fills a second workspace and checks every table and GET route; a new table or route fails until it is covered.
- Workspaces in the schema (migration `0005_workspaces`): every row has a `workspace_id`, and portfolio, project, task, resource and knowledge ids are unique per workspace, with composite foreign keys so a row cannot point into another workspace. Existing data moves into the `default` workspace; nothing changes for a single workspace.
- `MA_PMO_DEFAULT_PORTFOLIO` names the portfolio used when a caller gives none; `GET /allocations` takes `scope`.

## [0.5.0] - 2026-11-07

### Changed
- One executor (`ma_pmo/core/executor.py`): scenarios and goals both compile a `WorkflowSpec` to a LangGraph graph. Steps follow `needs`, so independent steps run in parallel and joins wait. `/orchestrate` gains `pause_on_gate`, a `status` in its response, and resume after a crash. A run keeps the workflow it started with.
- The 20 lifecycle scenarios are data (`ma_pmo/fixtures/workflows.json`), validated as `WorkflowSpec`: unique steps, known dependencies, no cycles. Golden traces pin their results in both languages.
- Workers are declared once in `ma_pmo/agents/registry.py` (`AgentSpec`). Routing, the graph, scenarios and the orchestrator prompt read from it, and agents are built on first use.

### Fixed
- Postgres sessions are pinned to UTC; on a server in another time zone every timestamp was shifted (nine hours in Asia/Seoul), which distorted approval latency.
- The API image installs from `pyproject.toml` and stays on Python 3.11: 3.15 cannot build `tiktoken` in a slim image, and the hand-kept dependency list had missed `alembic`.

### Added
- Your own workflows: JSON files in `MA_PMO_WORKFLOWS_DIR` run like built-in scenarios, including plugin agents.
- Agent plugins ([docs/PLUGINS.md](docs/PLUGINS.md)): packages add worker agents through the `ma_pmo.agents` entry-point group, build on the stable `ma_pmo.sdk`, and check themselves with `assert_agent_contract`. `ma-pmo agents` and `GET /agents` list them; a plugin that cannot load is reported and skipped. Example package in `examples/agent-plugin`.
- Approvals can really stop a run: `POST /scenarios/{id}/run?pause_on_gate=true` waits at a gate (`waiting_approval`); approving resumes from the next step, rejecting cancels the run. The default is unchanged.
- Recovery: a run whose process died is marked `interrupted` and continues with `POST /runs/{id}/resume`. Finished steps are reused, a lease gives each run to one process, and retried steps cannot write the same message or KPI twice.
- Postgres is a first-class backend: `ma-pmo[postgres]` keeps LangGraph checkpoints in the same database, so they survive restarts; migrations take an advisory lock when replicas start together; the full test suite runs on Postgres 16 in CI.
- CI builds the API image and checks `/health`.
- Run records: every scenario and orchestrated goal is stored as a run with its agent steps (`GET /runs`, `GET /runs/{id}`, `run_id` in responses), and messages, approvals and KPI events link to their run. Behaviour is unchanged.
- Schema migrations (Alembic, shipped in the package): `ma-pmo db upgrade` and `ma-pmo db status`. New databases are created through migrations; databases from 0.4 and earlier are recognized and adopted with their data.

## [0.4.0] - 2026-11-05

### Added
- API authentication middleware ([docs/AUTH.md](docs/AUTH.md)): `MA_PMO_AUTH_MODE=off|api_key|custom` (default `off`), API keys with roles `viewer`, `operator`, `approver`, `admin`, a route policy, a pluggable authenticator for SSO/OIDC or proxy headers, and `GET /auth/whoami`.
- The dashboard sends `NEXT_PUBLIC_API_KEY` as `X-API-Key` when set.
- GitHub and Linear trackers ([docs/INTEGRATIONS.md](docs/INTEGRATIONS.md#github)): `MA_PMO_INTEGRATIONS=github` (`GITHUB_REPOS`, optional `GITHUB_TOKEN`) or `linear` (`LINEAR_API_KEY`, `LINEAR_TEAM_KEYS`). Jira, GitHub and Linear now share one set of project rules (`ma_pmo/integrations/mapping.py`).
- Vector search for A7 ([docs/INTEGRATIONS.md](docs/INTEGRATIONS.md#vector-search-for-lessons-learned-a7)): `MA_PMO_RETRIEVER=vector` with offline character n-gram vectors, or any LiteLLM embedding model via `MA_PMO_EMBEDDING_MODEL`; falls back to lexical search when the model is unreachable. `ma-pmo eval --retrieval` reports recall@k and MRR on 14 labeled English/Korean queries (lexical MRR 0.774 → vector 0.964). Lexical search stays the default.
- Resource calendars for A3 ([docs/INTEGRATIONS.md](docs/INTEGRATIONS.md#resource-calendars-ics)): `MA_PMO_CALENDAR_DIR` with one `<resource_id>.ics` per person; busy hours (Mon–Fri, max 8 h/day, all-day events block the day, free/cancelled ignored) come off weekly capacity before allocation, and utilization is measured against the hours people actually had. Replaces the `NotImplementedError` stub; unchanged results when not configured.
- Confidence calibration of the HITL gate (`ma_pmo/eval/calibration.py`): ECE, Brier score, reliability bins and distinct confidence values from A4 risk alerts (against risk labels) and resolved approvals, plus a threshold what-if table. Shown by `ma-pmo eval`, `GET /eval` (`calibration`) and report section 4. Messages flagged `human_gate_required` count as reviewed at every threshold.
- OpenTelemetry tracing ([infra/otel](infra/otel/README.md)), extra `ma-pmo[otel]`, off unless `OTEL_ENABLED=true`: one trace per scenario run (`invoke_workflow` → `invoke_agent` → `chat`) with GenAI semantic-convention attributes, failed LLM calls recorded as errors, and deterministic fallbacks marked (`ma_pmo.fallback`). Jaeger compose file for local viewing.
- MCP server ([docs/MCP.md](docs/MCP.md)): `ma-pmo mcp` (stdio, extra `ma-pmo[mcp]`) with eight tools — portfolio status, CPM schedule, risks, pending approvals, scenarios, scenario runs, H1–H5 verdicts, lessons learned. Approving is not a tool.

### Added (course)
- Course: lecture 8 "Operating agents: identity, traces, calibration" (EN/KO); Lab 5 "Write an MCP tool" (needs the `mcp` extra) and Lab 6 "Calibrate the approval gate" with starters, solutions and checks; lectures 3, 4, 5 and 7 point at tracing, authentication, calibration, retrieval quality, the new trackers and MCP.

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

[Unreleased]: https://github.com/ma-pmo/ma-pmo-ext/compare/v0.6.0...HEAD
[0.6.0]: https://github.com/ma-pmo/ma-pmo-ext/compare/v0.5.0...v0.6.0
[0.5.0]: https://github.com/ma-pmo/ma-pmo-ext/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/ma-pmo/ma-pmo-ext/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/ma-pmo/ma-pmo-ext/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/ma-pmo/ma-pmo-ext/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/ma-pmo/ma-pmo-ext/releases/tag/v0.1.0

---

## 변경 내역 (한국어)

### [Unreleased]

### [0.6.0] - 2026-11-08

- 변경: README 스크린샷과 데모 GIF에 새 워크플로·비용 화면을 넣었습니다. 화면에 보이는 예시 비용, 예산, 추천은 `docs/capture_seed.py`로 만들며, 어떤 제공자도 호출하지 않습니다.
- 수정: 대시보드가 실행·버전·승인 시각을 UTC가 아니라 현지 시각인 것처럼 보여 주던 문제(Asia/Seoul에서 9시간 이르게 표시). 날짜 형식도 UI 언어가 아니라 브라우저 설정을 따랐습니다. 이제 UTC로 읽어 현지 시각으로, UI 언어 형식에 맞춰 보여 줍니다.
- 수정: 휴대폰에서 상단 바가 비좁던 문제. 공간이 모자라면 화면 이름을 줄이고, API 상태는 점만 보여 줍니다(글자는 화면 낭독기와 툴팁으로 남습니다).
- 수정: 시험 실행이 임시 워크스페이스의 LLM 비용을 버리고 예산도 무시하던 문제. 이제 그 비용이 워크스페이스 원장에 남고(`purpose: dry_run`), 워크스페이스 예산이 적용됩니다.
- 수정: 한 포트폴리오를 배분하면 모든 포트폴리오의 계획이 지워지던 문제. 이제 A3는 자기 계획만 교체하고, 없는 범위는 아무것도 지우지 않습니다.
- 수정: 두 포트폴리오가 공유하는 사람이 이중 배정될 수 있던 문제. 다른 포트폴리오에 잡힌 시간은 이제 바쁜 시간으로 계산합니다.
- 수정: 배분이 항상 2026-W03에서 시작하고 연도를 넘지 못하던 문제. 포트폴리오에 `plan_start`(ISO 주차, `portfolio.csv`의 선택 열)를 지정할 수 있고, 없으면 이번 주부터 시작합니다. 샘플 포트폴리오는 2026-W03을 유지합니다.
- 추가: 재생 평가기와 모델 추천(로드맵 6 완료, 마이그레이션 `0011_recommendations`). 워크플로 단계 하나를 빠른 모델로 데모 데이터에서 쪽당 `N`번 재생해, 단계 비용, 올바른 출력 비율, (리스크 단계는) 리스크 판정 정확도를 95% 부트스트랩 구간과 함께 비교하고 추천·추천 안 함·판단 불가로 판정합니다. approver가 승인하면 변경을 담은 초안이 저장되며, 저절로 게시되는 것은 없습니다. `ma-pmo replay`, `ma-pmo recommendation`, `/recommendations`, 비용 화면의 모델 추천.
- 추가: 단계별 모델 선택. 워크플로 단계에 `"model_tier": "fast"`를 주면 그동안 설정만 있고 쓰이지 않던 `LLM_MODEL_FAST`를 쓰고, 나머지는 `LLM_MODEL`을 그대로 씁니다. 워크플로 편집기의 모델 칸에서 고르며, 단계 표와 그래프에 표시되고, 원장의 모델별 비용으로 효과를 봅니다. Anthropic 모델에서는 시스템 프롬프트를 캐시 가능으로 표시합니다(`LLM_PROMPT_CACHE`, 기본 켬).
- 추가: 예산(마이그레이션 `0010_budgets`). 워크스페이스마다 월 예산과 실행 1회 예산을 두고, 각각 경고 금액과 한도(USD)를 정합니다. 경고 금액을 넘으면 한 번 알리고(`budget.warning` 이벤트), 한도를 넘으면 에이전트가 LLM 대신 결정론적 방식으로 동작해 실행은 성공하며, 그 사실이 표시됩니다(실행과 결과의 `budget_fallback`, 워크플로 화면의 표시, 비용 화면의 목록). 비용 화면, `ma-pmo budget`, `PUT /budgets/{month|run}`(admin)으로 정합니다.
- 추가: 비용 원장(로드맵 6, 마이그레이션 `0009_llm_calls`). 모든 LLM 호출을 실행, 단계, 에이전트, 모델, 토큰(캐시 읽기·쓰기 따로), USD와 함께 기록합니다. 가격은 버전이 있는 가격표(직접 지정한 `MA_PMO_PRICE_TABLE` 또는 고정된 LiteLLM 버전에 포함된 표)로 계산하며, 모르는 가격은 추정하지 않고 null로 두어 "가격 미상"으로 셉니다. **비용** 화면과 `GET /costs?by=model|agent|workflow|run|day`, 실행별 단계 비용 `GET /runs/{id}/costs`로 봅니다. [docs/COSTS.ko.md](docs/COSTS.ko.md) 참고.
- 추가: 워크플로 편집기(로드맵 5 완료). 워크플로 화면의 **편집**을 누르면 입력 양식에서 단계를 추가·삭제하고 순서를 바꾸며, 각 단계가 기다릴 단계와 매개변수를 정합니다. 입력하는 동안 서버 검증기가 검사하고 그래프가 바로 바뀌며, 사용 중인 버전의 필수 단계는 잠깁니다. **데모 데이터로 시험 실행**(`POST /workflows/dry-run`)은 초안을 임시 워크스페이스에서 샘플 포트폴리오로 실행하고 지웁니다. 실제 데이터, 승인, 알림은 건드리지 않으며, Jira·GitHub·Linear가 설정되어 있어도 데모 데이터를 읽습니다. 초안을 저장한 뒤 버전 표에서 게시합니다. 휴대폰에서는 읽기 전용입니다.
- 추가: 워크플로 버전(마이그레이션 `0008_workflow_versions`, 다른 테이블처럼 행 수준 보안 적용). 워크플로를 바뀌지 않는 **초안**으로 저장하고, `approver`나 `admin`이 **게시**하면 그 워크스페이스에서 실행됩니다. 모든 버전을 계속 볼 수 있고(워크플로 화면의 버전 표, `GET /workflows/{id}/versions[/{v}]`), 각 실행은 사용한 버전을 기록합니다(`GET /runs`의 `workflow_version`, 실행 메뉴에 표시). API(`POST /workflows/validate`, 422와 `detail.problems`), CLI(`ma-pmo workflow validate | draft | versions | publish`), 대시보드가 같은 검증기를 씁니다. 없는 에이전트·분류, 필수가 아닌 게이트 단계, 필수 단계를 빼거나 바꾸는 것을 거부하며, 게시할 때 다시 검사합니다. `/scenarios`, 시나리오 실행, MCP 도구는 사용 중인 버전을 씁니다.
- 추가: 워크플로 보기의 실시간 실행 상태. 실행을 고르면(또는 시나리오 결과의 **워크플로에서 보기**) 각 단계를 완료, 실행 중, 승인 대기, 실패, 시작 전으로 색칠하고, 표에 오류와 재시도 횟수를 보여 주며, 실행 중에는 2초마다 갱신합니다. 그래프는 그 실행이 저장한 워크플로 그대로이고, 지금 파일과 다르면 표시합니다. `GET /runs/{id}/workflow`로 받을 수 있고, `GET /runs`가 `workflow`를 받습니다.
- 추가: 워크플로 보기(로드맵 5, 읽기 전용). **워크플로** 화면이 각 워크플로를 병렬로 실행될 수 있는 단계별 열로 그리고, 기다리는 단계로 화살표를 잇고, 필수 단계(게이트)를 표시하며, 같은 단계를 표로도 보여 줍니다. 모든 단계에 키보드로 이동할 수 있고, 휴대폰에서는 목록 대신 메뉴를 씁니다. `GET /workflows`는 기본·사용자 워크플로(와 불러오지 못한 파일)를, `GET /workflows/{id}`는 각 단계의 실제 `needs`와 `level`을 돌려줍니다. 그래프 라이브러리는 추가하지 않았습니다.
- 추가: 대시보드 워크스페이스·포트폴리오 선택(사이드바). 호출자가 들어갈 수 있는 곳만 보여 주고, 고른 것을 기억하며, 모든 요청에 `X-Workspace`를 보냅니다. 대시보드의 현황, 리스크, 배분, 일정 산출, 게이트 심사, 목표 실행이 고른 포트폴리오를 따릅니다. `GET /workspaces`(호출자의 워크스페이스와 그곳의 역할, `X-Workspace` 불필요)와 `GET /portfolios`를 추가하고, `GET /risks`가 `scope`를 받습니다.
- 추가: Postgres 행 수준 보안(마이그레이션 `0007_row_level_security`). API 필터 뒤에서 데이터베이스가 직접 워크스페이스를 분리합니다. 트랜잭션마다 워크스페이스를 Postgres에 알리며, 다른 워크스페이스의 행은 보이지도 않고 쓸 수도 없습니다. 일반 역할에만 적용되므로 compose 파일과 Kubernetes 매니페스트는 이제 `postgres` 관리자로 Postgres를 띄우고, 데이터베이스를 소유한 일반 역할 `mapmo`를 만듭니다([deploy/README.ko.md](deploy/README.ko.md#postgres-역할), 기존 데이터베이스를 옮기는 방법 포함). CI는 Postgres 테스트를 그런 역할로 실행하고, compose Postgres에서 API 이미지를 띄워 확인합니다.
- 추가: 워크스페이스 멤버십. 할 수 있는 일을 워크스페이스마다 정합니다. 키에 `워크스페이스/역할`로 쓴 역할은 그곳에서만 적용되고, `ma-pmo workspace create | list | members | grant | revoke`로 멤버십을 데이터베이스에 둡니다(마이그레이션 `0006_memberships`). 역할이 없는 워크스페이스는 없는 워크스페이스와 똑같이 404입니다. 일반 역할은 계속 모든 곳에 적용되므로 기존 키는 그대로 동작합니다. `GET /auth/whoami`에 `workspace`가 추가됩니다.
- 변경: 역할이 하나도 없는 주체는 더 이상 읽을 수 없습니다. 역할 없이 `Principal(subject)`를 돌려주던 직접 만든 인증기는 모든 데이터를 읽을 수 있었지만, 이제는 멤버십이 없으면 접근할 수 없습니다.
- 추가: 워크스페이스 격리. 요청은 `X-Workspace`로 지정한 워크스페이스에서 실행됩니다(CLI, MCP, 백그라운드 작업은 `MA_PMO_WORKSPACE`). 모든 ORM 조회, 조인, 서브쿼리가 자동으로 걸러지고 새 행도 그 워크스페이스에 생깁니다. 다른 워크스페이스의 id는 찾을 수 없습니다(`POST /approvals/{id}`는 없는 승인에 400 대신 404). 두 번째 워크스페이스를 채워 모든 테이블과 GET 경로를 검사하는 테스트가 있으며, 새 테이블이나 경로는 검사에 넣기 전까지 실패합니다.
- 추가: 스키마에 워크스페이스(마이그레이션 `0005_workspaces`). 모든 행에 `workspace_id`가 있고, 포트폴리오·프로젝트·태스크·자원·지식 id는 워크스페이스 안에서만 고유합니다. 복합 외래 키로 다른 워크스페이스의 행을 가리킬 수 없습니다. 기존 데이터는 `default` 워크스페이스로 옮겨지며, 워크스페이스 하나만 쓰면 달라지는 것이 없습니다.
- 추가: `MA_PMO_DEFAULT_PORTFOLIO`로 호출자가 지정하지 않을 때 쓸 포트폴리오를 정합니다. `GET /allocations`는 `scope`를 받습니다.

### [0.5.0] - 2026-11-07

- 실행기 통합(`ma_pmo/core/executor.py`): 시나리오와 목표 모두 `WorkflowSpec`을 LangGraph 그래프로 컴파일해 실행합니다. `needs`대로 실행되어 독립 단계는 병렬로, 합류 단계는 기다렸다가 돕니다. `/orchestrate`에 `pause_on_gate`, 응답의 `status`, 장애 후 재개가 추가됩니다. 실행은 시작할 때의 워크플로를 유지합니다.
- 시나리오 20개를 데이터(`ma_pmo/fixtures/workflows.json`)로 옮겨 `WorkflowSpec`으로 검증(단계 중복, 없는 의존, 순환). 두 언어의 golden trace로 결과를 고정합니다. 내 워크플로는 `MA_PMO_WORKFLOWS_DIR`의 JSON으로 추가하며 플러그인 에이전트도 쓸 수 있습니다.
- 에이전트 플러그인([docs/PLUGINS.ko.md](docs/PLUGINS.ko.md)): 외부 패키지가 `ma_pmo.agents` entry point로 에이전트를 추가하고, 안정 API `ma_pmo.sdk` 위에 만들며, `assert_agent_contract`로 스스로 검사합니다. `ma-pmo agents`, `GET /agents`로 확인하고, 불러오지 못한 플러그인은 알리고 건너뜁니다. 예제 패키지는 `examples/agent-plugin`.
- 작업자 에이전트를 `ma_pmo/agents/registry.py`(`AgentSpec`) 한 곳에 선언. 라우팅, 그래프, 시나리오, 오케스트레이터 프롬프트가 여기서 읽고, 에이전트는 처음 쓸 때 만들어집니다.
- 수정: Postgres 세션을 UTC로 고정. 서버 시간대가 다르면 모든 시각이 밀렸습니다(Asia/Seoul에서 9시간). 승인 지연 측정이 왜곡되던 문제입니다.
- 수정: API 이미지를 `pyproject.toml`로 설치하고 Python 3.11을 유지. 3.15는 slim 이미지에서 `tiktoken`을 빌드할 수 없고, 손으로 관리하던 의존성 목록에 `alembic`이 빠져 있었습니다.
- 승인이 실제로 실행을 멈출 수 있습니다: `POST /scenarios/{id}/run?pause_on_gate=true`는 게이트에서 대기하고(`waiting_approval`), 승인하면 다음 단계부터 이어 가며 반려하면 취소됩니다. 기본 동작은 그대로입니다.
- 복구: 프로세스가 죽은 실행은 `interrupted`로 표시되고 `POST /runs/{id}/resume`으로 이어 갑니다. 끝난 단계는 재사용하고, 임대(lease)가 실행을 한 프로세스에만 주며, 재시도해도 같은 메시지·KPI가 두 번 쓰이지 않습니다.
- Postgres 정식 지원: `ma-pmo[postgres]`로 LangGraph 체크포인트를 같은 DB에 저장해 재시작 후에도 유지하고, 복제본이 동시에 시작해도 마이그레이션이 잠금으로 순서를 지키며, CI에서 전체 테스트를 Postgres 16으로 실행합니다.
- CI가 API 이미지를 빌드하고 `/health`를 확인합니다.
- 실행 기록: 시나리오와 오케스트레이션 실행이 에이전트 단계와 함께 저장되고(`GET /runs`, `GET /runs/{id}`, 응답의 `run_id`), 메시지·승인·KPI가 해당 실행에 연결됩니다. 기존 동작은 바뀌지 않습니다.
- 스키마 마이그레이션(Alembic, 패키지에 포함): `ma-pmo db upgrade`, `ma-pmo db status`. 새 데이터베이스도 마이그레이션으로 만들고, 0.4 이하 데이터베이스는 자동으로 인식해 데이터를 유지한 채 이어받습니다.

### [0.4.0] - 2026-11-05

- API 인증 미들웨어([docs/AUTH.ko.md](docs/AUTH.ko.md)): `MA_PMO_AUTH_MODE=off|api_key|custom`(기본 `off`), 역할(`viewer`, `operator`, `approver`, `admin`)이 있는 API 키, 경로별 권한 정책, SSO/OIDC·프록시 헤더용 인증기 플러그인, `GET /auth/whoami`.
- 대시보드는 `NEXT_PUBLIC_API_KEY`가 있으면 `X-API-Key`로 보냅니다.
- GitHub·Linear 트래커([docs/INTEGRATIONS.ko.md](docs/INTEGRATIONS.ko.md)): `MA_PMO_INTEGRATIONS=github`(`GITHUB_REPOS`, 선택 `GITHUB_TOKEN`) 또는 `linear`(`LINEAR_API_KEY`, `LINEAR_TEAM_KEYS`). Jira·GitHub·Linear가 같은 프로젝트 규칙(`ma_pmo/integrations/mapping.py`)을 공유.
- A7 벡터 검색([docs/INTEGRATIONS.ko.md](docs/INTEGRATIONS.ko.md)): `MA_PMO_RETRIEVER=vector`(오프라인 문자 n-gram 벡터) 또는 `MA_PMO_EMBEDDING_MODEL`로 LiteLLM 임베딩 모델 사용, 모델에 연결할 수 없으면 어휘 검색으로 대체. `ma-pmo eval --retrieval`로 영어·한국어 라벨 질의 14개의 recall@k·MRR 측정(어휘 MRR 0.774 → 벡터 0.964). 기본값은 어휘 검색 유지.
- A3용 자원 캘린더([docs/INTEGRATIONS.ko.md](docs/INTEGRATIONS.ko.md)): `MA_PMO_CALENDAR_DIR`에 사람별 `<resource_id>.ics`를 두면 바쁜 시간(월~금, 하루 최대 8시간, 종일 일정은 하루 전체, 한가함·취소 일정 제외)을 주간 가용 시간에서 빼고 배정하며, 활용률도 실제 가용 시간 기준으로 계산. 기존 미구현 스텁 대체, 설정하지 않으면 결과 동일.
- HITL 게이트의 확신도 보정 측정(`ma_pmo/eval/calibration.py`): A4 리스크 경보(레이블 대비)와 처리된 승인으로 ECE, Brier 점수, 구간별 신뢰도, 확신도 값 종류를 계산하고, 기준값별 검토 대상과 빠져나간 오류를 표로 보여 줌. `ma-pmo eval`, `GET /eval`(`calibration`), 보고서 4절.
- OpenTelemetry 추적([infra/otel](infra/otel/README.md)), extra `ma-pmo[otel]`, `OTEL_ENABLED=true`일 때만 동작: 시나리오 실행마다 트레이스 하나(`invoke_workflow` → `invoke_agent` → `chat`), GenAI 시맨틱 규약 속성, 실패한 LLM 호출은 오류로, 대체 경로 사용은 `ma_pmo.fallback`으로 표시. 로컬 확인용 Jaeger compose 파일.
- MCP 서버([docs/MCP.ko.md](docs/MCP.ko.md)): `ma-pmo mcp`(stdio, extra `ma-pmo[mcp]`)로 포트폴리오 현황, CPM 일정, 리스크, 승인 대기, 시나리오 목록·실행, H1~H5 판정, 과거 교훈 도구 8개 제공. 승인은 도구로 제공하지 않음.
- 교육 과정: 8강 "에이전트 운영하기: 신원, 추적, 보정"(영어·한국어), 실습 5 "MCP 도구 만들기"(`mcp` extra 필요)와 실습 6 "승인 게이트 보정하기"(시작 코드·정답·채점), 3·4·5·7강에 추적·인증·보정·검색 품질·새 트래커·MCP 안내 추가.
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
