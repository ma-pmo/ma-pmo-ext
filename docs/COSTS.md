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
