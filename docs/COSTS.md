# LLM costs

**English | [한국어](COSTS.ko.md)**

Every LLM call is written to a cost ledger: the run and step it belongs to, the agent, the
model, the tokens the provider reported, and what that cost in USD. Agents without an LLM (or
running without an API key) use their deterministic fallbacks and cost nothing.

## Where to see it

- Dashboard → **Costs**: totals, then by model, agent, workflow, day and run, for the last 7, 30
  or 90 days or all time.
- `GET /costs?by=model|agent|workflow|run|day&days=30`: the same as JSON.
- `GET /runs/{run_id}/costs`: one run, per step.

Like everything else, the ledger belongs to a workspace (row-level security on Postgres).

## Budgets

Each workspace can set two budgets, each with a **warning** and a **hard limit** in USD:

| Budget | Counts |
|---|---|
| `month` | everything the workspace spent this calendar month (UTC) |
| `run` | what one run has spent |

Before every LLM call the spend so far is checked:

- past a **warning**, people are told once (a log line and a `budget.warning` event to the
  enabled notifiers: once per month for `month`, once per run for `run`); nothing stops;
- past a **hard limit**, the call is not made. Every agent already answers a failed call with
  its deterministic fallback, so **the run carries on and succeeds**. The run records why
  (`budget_fallback` in `GET /runs`, in the scenario or goal result, and as a badge on the
  workflow view), and the Costs page lists such runs.

The call that crosses a limit has already been made, so a limit can be passed by at most one
call. Unpriced calls do not count. A limit of `0` means no LLM call at all.

Set them on the Costs page, or:

```bash
ma-pmo budget set month --warn 40 --limit 50
ma-pmo budget set run --limit 0.50
ma-pmo budget show
ma-pmo budget clear run
```

`GET /budgets` shows them with this month's spend; `PUT /budgets/{month|run}` with
`{"warn_usd": …, "limit_usd": …}` changes them (both `null` removes it) and needs the `admin`
role.

## Prices

Prices come from a versioned table, and each ledger row records which one priced it:

1. your own JSON file, if `MA_PMO_PRICE_TABLE` points to one;
2. otherwise the table bundled with the installed LiteLLM (its version is pinned in `uv.lock`,
   so an upgrade is a visible change).

A model neither table knows is **not priced**: its calls are counted under "unpriced calls" and
left out of the USD total, never guessed. Local models (Ollama) are priced at zero by LiteLLM.

Your own table, in USD per million tokens (`cache_read` and `cache_write` default to `input`):

```json
{"version": "acme-2026-11",
 "models": {
   "anthropic/claude-sonnet-5": {"input": 3.0, "output": 15.0, "cache_read": 0.3, "cache_write": 3.75},
   "acme/in-house-model": {"input": 0.4, "output": 0.4}
 }}
```

A model is looked up as written and, for `provider/name`, also as `name`.

## How tokens are counted

The ledger keeps the provider's usage as LiteLLM reports it: `prompt_tokens` includes input read
from or written to the prompt cache, which is also kept apart (`cache_read_tokens`,
`cache_write_tokens`). The price is

```
(prompt - cache read - cache write) × input + cache read × cache_read
  + cache write × cache_write + completion × output
```

which is the same as LiteLLM's own `completion_cost` for the same response; the tests check this
on provider-shaped usage, with and without caching. A retried call is real spend and counts again.
Recording never breaks an agent's call: if writing the row fails, the call goes on and a warning
is logged.
