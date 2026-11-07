# AGENTS.md

Guidance for AI coding tools and new contributors working in this repository. The full guide
is [CONTRIBUTING.md](CONTRIBUTING.md); this is the short, checkable version.

## Setup and checks

```bash
make dev            # Python deps + .env
make db-init        # SQLite schema + demo fixtures
make test-smoke     # seconds: the app boots and the main paths work
make test           # full pytest suite
make lint           # ruff check . && mypy ma_pmo
make web            # Next.js dashboard on :3000 (apps/web)
```

Everything runs offline. No API key is needed: every LLM step has a deterministic fallback, and
tests must not depend on network access or an LLM.

## Map

| Path | What lives there |
|---|---|
| `ma_pmo/agents/` | A1 orchestrator, A2 planning (CPM), A3 resources, A4 risk, A5 reporting, A6 governance, A7 knowledge |
| `ma_pmo/core/` | message schemas and protocol, KPIs, HITL approvals, i18n, scenarios, LangGraph |
| `ma_pmo/integrations/` | notifier/tracker plugins (Slack, webhook, Jira) and the registry |
| `ma_pmo/eval/`, `ma_pmo/harness/` | H1–H5 evaluation, data/report templates, experiment harness |
| `ma_pmo/learn/` | course labs: starters, solutions, checks (`ma-pmo learn`) |
| `ma_pmo/api/` | FastAPI app, routers and auth (`auth.py`) |
| `ma_pmo/agents/registry.py`, `ma_pmo/sdk/` | worker specs and plugin loading; the SDK is the only public, semver-stable surface for plugins |
| `ma_pmo/mcp_server.py` | MCP server (`ma-pmo mcp`); approvals are never a tool |
| `apps/web/` | Next.js admin dashboard |
| `docs/` | integration guide, paper validation guide, course (`docs/learn/`), screenshots |
| `tests/` | pytest; markers `smoke` and `regression` |

## Rules

1. **Messages are contracts.** Agents exchange `AgentMessage` with a versioned payload schema
   (`name.v1`) from `ma_pmo/core/schemas/`. Do not pass free-form dicts between agents. A
   breaking payload change is a new version.
2. **Every LLM step has a fallback** that returns the same schema. Catch the LLM failure, log
   it, call `tracing.mark_fallback(...)`, and fall back; never swallow errors from our own code.
3. **High-risk or low-confidence decisions go through HITL** (`human_gate_required`, or
   confidence below `HITL_CONFIDENCE_THRESHOLD`). Do not add a path that skips `protocol.publish`.
   Writes in a run step need a `runs.dedupe_key(...)`, so a retried step cannot repeat them.
4. **New endpoints are covered by the auth policy.** `required_role()` in
   `ma_pmo/api/auth.py` maps method and path to a role; add a rule there if a new `POST` needs
   more than `operator`, and add a case to `tests/test_auth.py`. Take the caller with
   `principal: CurrentPrincipal`, never from the request body.
5. **Integrations are best effort.** Notifiers raise on failure; `dispatch.emit` records it and
   the agents keep running. Trackers return `found: False` instead of raising for unknown data.
   Status endpoints never return secret values.
6. **Bilingual by default.** User-facing backend text uses `tr("English", "한국어")`
   (`ma_pmo/core/i18n.py`). Dashboard strings go in both `en` and `ko` in
   `apps/web/app/lib/messages.ts`. Docs: English `*.md` with a Korean `*.ko.md` next to it.
   Code, comments and docstrings are in English.
7. **Schema changes need a migration** in `ma_pmo/db/migrations/versions/`.
   `tests/test_migrations.py` fails when models and migrations differ. Never call
   `Base.metadata.create_all`; use `ensure_schema()`.
8. **Workflows are data, and one executor runs them.** Edit `ma_pmo/fixtures/workflows.json`,
   not Python, and do not add a second way to run agents: use `ma_pmo/core/executor.py`.
   `tests/golden/` pins what every scenario does; regenerate it only for an intended change.
9. **Tests with every change.** New behavior gets a test; mark end-to-end checks `smoke`. If a
   pinned result in `tests/test_regression.py` changes on purpose, update it in the same change
   and say why.
10. **Evaluation data stays isolated.** `--data` evaluations use their own SQLite file
   (`eval/workflow.use_isolated_db`); lab 3 does the same. Do not write into the demo database
   from tools or tests that process user data.
11. **Course labs** live in `ma_pmo/learn/labs/labN_slug/` with `starter/`, `solution/`,
   `README.md`, `README.ko.md`, and checks in `ma_pmo/learn/checks.py`. Every failed check needs
   a hint. `tests/test_learn.py` must show the solution passes and the starter fails.
12. **Style.** ruff (line length 100) and mypy must pass. Match the surrounding code; keep
   comments short and about *why*.

## Do not

- Commit secrets, `.env`, local databases (`*.db`, `.ma-pmo-eval.db*`, `.ma-pmo-learn.db*`) or
  build caches.
- Add personal or company-specific data to fixtures, docs or screenshots.
- Change the dual-license terms (AGPL-3.0-or-later + commercial) or the trademark policy.
