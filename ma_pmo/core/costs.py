"""The cost ledger: every LLM call with its run, step, agent, model, tokens and USD.

Prices come from a versioned table: your own JSON file (`MA_PMO_PRICE_TABLE`) if set, else the
table bundled with the installed LiteLLM (version pinned in uv.lock). A model with no price stays
`null`: the ledger never guesses. Each row records which table priced it.

Your own table:

    {"version": "acme-2026-11",
     "models": {"anthropic/claude-sonnet-5": {"input": 3.0, "output": 15.0,
                                              "cache_read": 0.3, "cache_write": 3.75}}}

Prices are USD per million tokens; `cache_read` and `cache_write` default to `input`.

Tokens follow LiteLLM's usage: `prompt_tokens` includes cached input, `cached_tokens` is what was
read from the cache and `cache_creation_tokens` what was written to it, so uncached input is
prompt - read - written.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from importlib.metadata import version
from pathlib import Path
from typing import Any

from sqlalchemy import func, select

from ma_pmo.core.config import get_settings
from ma_pmo.core.obs import get_logger
from ma_pmo.core.runs import current_run_id, current_step_seq
from ma_pmo.db.models import LlmCall, Run
from ma_pmo.db.session import get_session

_log = get_logger("costs")
MILLION = 1_000_000


@dataclass(frozen=True)
class Price:
    """USD per token."""

    input: float
    output: float
    cache_read: float
    cache_write: float


@dataclass(frozen=True)
class Usage:
    prompt: int = 0
    completion: int = 0
    cache_read: int = 0
    cache_write: int = 0


def usage_of(response: Any) -> Usage:
    """Token counts from a LiteLLM response (missing fields count as 0)."""
    usage = getattr(response, "usage", None)
    details = getattr(usage, "prompt_tokens_details", None)

    def num(obj: Any, name: str) -> int:
        value = getattr(obj, name, None) if obj is not None else None
        return int(value or 0)

    read = num(details, "cached_tokens") or num(usage, "cache_read_input_tokens")
    written = num(details, "cache_creation_tokens") or num(usage, "cache_creation_input_tokens")
    return Usage(num(usage, "prompt_tokens"), num(usage, "completion_tokens"), read, written)


@lru_cache(maxsize=4)
def _table(path: str) -> tuple[str, dict[str, Price]]:
    if path:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        prices = {}
        for model, p in data.get("models", {}).items():
            base = float(p["input"]) / MILLION
            prices[model] = Price(base, float(p["output"]) / MILLION,
                                  float(p.get("cache_read", p["input"])) / MILLION,
                                  float(p.get("cache_write", p["input"])) / MILLION)
        return str(data.get("version") or Path(path).name), prices
    import litellm

    prices = {}
    for model, p in litellm.model_cost.items():
        if not isinstance(p, dict) or p.get("input_cost_per_token") is None \
                or p.get("output_cost_per_token") is None:
            continue
        base = float(p["input_cost_per_token"])
        prices[model] = Price(base, float(p["output_cost_per_token"]),
                              float(p.get("cache_read_input_token_cost") or base),
                              float(p.get("cache_creation_input_token_cost") or base))
    return f"litellm {version('litellm')}", prices


def price_of(model: str) -> tuple[Price | None, str]:
    """The price of a model and the table it came from; None if the table does not know it.

    `anthropic/claude-x` is also looked up as `claude-x`, as LiteLLM names them both ways.
    """
    table, prices = _table(get_settings().price_table)
    found = prices.get(model)
    if found is None and "/" in model:
        found = prices.get(model.split("/", 1)[1])
    return found, table


def usd(usage: Usage, price: Price | None) -> float | None:
    if price is None:
        return None
    uncached = max(0, usage.prompt - usage.cache_read - usage.cache_write)
    return (uncached * price.input + usage.cache_read * price.cache_read
            + usage.cache_write * price.cache_write + usage.completion * price.output)


def record(model: str, agent: str, usage: Usage, latency_ms: float) -> float | None:
    """Add a ledger row for one call; returns its USD (None if unpriced). Never raises."""
    try:
        price, table = price_of(model)
        cost = usd(usage, price)
        with get_session() as s:
            s.add(LlmCall(run_id=current_run_id(), step_seq=current_step_seq(), agent=agent,
                          model=model, prompt_tokens=usage.prompt,
                          completion_tokens=usage.completion, cache_read_tokens=usage.cache_read,
                          cache_write_tokens=usage.cache_write, usd=cost,
                          price_version=table if price else None, latency_ms=latency_ms))
        return cost
    except Exception as e:  # the ledger must never break an agent's call
        _log.warning("cost_record_failed", model=model, error=str(e))
        return None


GROUPS = {"model": LlmCall.model, "agent": LlmCall.agent, "run": LlmCall.run_id,
          "workflow": Run.workflow, "day": func.date(LlmCall.created_at),
          "step": LlmCall.step_seq, "purpose": func.coalesce(LlmCall.purpose, "run")}


def summary(by: str = "model", *, run_id: str | None = None, days: int | None = None) -> dict:
    """Totals and one row per group. `unpriced` counts calls whose cost is unknown."""
    if by not in GROUPS:
        raise ValueError(f"group by one of {', '.join(GROUPS)}")
    key = GROUPS[by]
    columns = (func.count(LlmCall.id), func.sum(LlmCall.prompt_tokens),
               func.sum(LlmCall.completion_tokens), func.sum(LlmCall.cache_read_tokens),
               func.sum(LlmCall.usd), func.count(LlmCall.id) - func.count(LlmCall.usd))

    def scoped(stmt: Any) -> Any:
        if by == "workflow":
            stmt = stmt.join(Run, Run.id == LlmCall.run_id)
        if run_id is not None:
            stmt = stmt.where(LlmCall.run_id == run_id)
        if days is not None:
            stmt = stmt.where(LlmCall.created_at >= datetime.now(UTC) - timedelta(days=days))
        return stmt

    def row(values: Any) -> dict:
        calls, prompt, completion, cached, cost, unpriced = values
        return {"calls": calls or 0, "prompt_tokens": prompt or 0,
                "completion_tokens": completion or 0, "cache_read_tokens": cached or 0,
                "usd": round(cost, 6) if cost is not None else None, "unpriced": unpriced or 0}

    with get_session() as s:
        rows = s.execute(scoped(select(key, *columns)).group_by(key)
                         .order_by(func.coalesce(func.sum(LlmCall.usd), 0).desc())).all()
        total = s.execute(scoped(select(*columns))).one()
    _, table = price_of("")
    return {"by": by, "price_table": table, "total": row(total),
            "rows": [{"key": str(r[0]) if r[0] is not None else None, **row(r[1:])}
                     for r in rows]}
