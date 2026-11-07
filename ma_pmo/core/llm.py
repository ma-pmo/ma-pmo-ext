"""LLM gateway — provider abstraction (LiteLLM), Anthropic Claude by default.

- swappable model (LLM_MODEL env); a workflow step can ask for the fast tier (LLM_MODEL_FAST)
- the system prompt is marked cacheable for providers that support prompt caching (Anthropic)
- token and latency usage reported as KPIs (cost axis)
- structured output: enforced Pydantic schema (JSON mode) — curbs hallucination/format errors
- natural-language output follows the active language (core/i18n.py)
"""
from __future__ import annotations

import json
import time
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, TypeVar

import litellm
from pydantic import BaseModel

from ma_pmo.core import budgets, costs, kpi, tracing
from ma_pmo.core.config import get_settings
from ma_pmo.core.i18n import get_lang

_settings = get_settings()
T = TypeVar("T", bound=BaseModel)

# LiteLLM global settings
litellm.drop_params = True  # drop unsupported params automatically (provider portability)

# the model tier of the workflow step running now (set by core/executor.py)
_tier: ContextVar[str | None] = ContextVar("ma_pmo_model_tier", default=None)


@contextmanager
def use_tier(tier: str | None) -> Iterator[None]:
    """Calls inside use the model of `tier`: "fast" is LLM_MODEL_FAST, anything else LLM_MODEL."""
    token = _tier.set(tier)
    try:
        yield
    finally:
        _tier.reset(token)


# when set (by core/replay.py), every structured call notes how it went
_outcomes: ContextVar[list[dict] | None] = ContextVar("ma_pmo_llm_outcomes", default=None)
VALID, RETRIED, INVALID, UNAVAILABLE = "valid", "valid_after_retry", "invalid", "unavailable"


@contextmanager
def observe() -> Iterator[list[dict]]:
    """Collect one row per structured call made inside: agent, model, step, run and outcome."""
    rows: list[dict] = []
    token = _outcomes.set(rows)
    try:
        yield rows
    finally:
        _outcomes.reset(token)


def _note(agent: str, model: str, outcome: str) -> None:
    rows = _outcomes.get()
    if rows is not None:
        from ma_pmo.core import runs

        rows.append({"agent": agent, "model": model, "outcome": outcome,
                     "run_id": runs.current_run_id(), "step": runs.current_step_seq()})


def model_for(tier: str | None = None) -> str:
    tier = tier if tier is not None else _tier.get()
    if tier == "fast" and _settings.llm_model_fast:
        return _settings.llm_model_fast
    return _settings.llm_model


def _caches(model: str) -> bool:
    return _settings.llm_prompt_cache and model.startswith(("anthropic/", "claude"))


def _messages(system: str, user: str, model: str) -> list[dict[str, Any]]:
    if _caches(model):  # the system prompt (role, schema) repeats; the provider reuses it
        content: Any = [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}]
    else:
        content = system
    return [{"role": "system", "content": content}, {"role": "user", "content": user}]


def _provider_kwargs(model: str) -> dict:
    """Per-provider auth/endpoint kwargs. Local providers such as Ollama need no key."""
    kw: dict = {}
    if model.startswith("anthropic/") and _settings.anthropic_api_key:
        kw["api_key"] = _settings.anthropic_api_key
    # local/private endpoint (Ollama, etc.)
    if _settings.llm_api_base:
        kw["api_base"] = _settings.llm_api_base
    # Ollama supports format=json for structured output
    if model.startswith(("ollama/", "ollama_chat/")):
        kw["format"] = "json"
    return kw


def complete(
    system: str,
    user: str,
    *,
    agent: str = "?",
    model: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> str:
    """Free-form completion. Usage is recorded on the KPI cost axis and in the cost ledger.

    Raises budgets.BudgetExceeded, before calling, once a hard budget is reached; callers fall
    back to their deterministic answer as for any other failed call.
    """
    model = model or model_for()
    budgets.check(agent)
    language = "Korean" if get_lang() == "ko" else "English"
    system = f"{system}\n\nWrite all natural-language text in {language}."
    t0 = time.monotonic()
    with tracing.span(f"chat {model}", {tracing.OPERATION: "chat", tracing.REQUEST_MODEL: model,
                                        tracing.AGENT_ID: agent}):
        resp = litellm.completion(
            model=model,
            messages=_messages(system, user, model),
            temperature=_settings.llm_temperature if temperature is None else temperature,
            max_tokens=max_tokens or _settings.llm_max_tokens,
            **_provider_kwargs(model),
        )
        usage = getattr(resp, "usage", None)
        tracing.set_attributes({
            tracing.INPUT_TOKENS: getattr(usage, "prompt_tokens", None),
            tracing.OUTPUT_TOKENS: getattr(usage, "completion_tokens", None),
        })
    latency_ms = (time.monotonic() - t0) * 1000
    costs.record(model, agent, costs.usage_of(resp), latency_ms)
    kpi.record_llm_cost(
        model=model,
        prompt_tokens=getattr(usage, "prompt_tokens", 0) or 0,
        completion_tokens=getattr(usage, "completion_tokens", 0) or 0,
        latency_ms=latency_ms,
        agent=agent,
    )
    return resp.choices[0].message.content or ""


def complete_structured(
    system: str,
    user: str,
    schema: type[T],
    *,
    agent: str = "?",
    model: str | None = None,
) -> T:
    """Structured output — validated against a Pydantic schema (one retry).

    Asks for JSON and, if validation fails, retries once with the schema in the prompt.
    """
    json_schema = json.dumps(schema.model_json_schema(), ensure_ascii=False)
    sys_full = (
        f"{system}\n\nOutput only a JSON object matching this JSON schema (no explanations):\n"
        f"{json_schema}"
    )
    used = model or model_for()
    try:
        raw = complete(sys_full, user, agent=agent, model=model, temperature=0.0)
    except Exception:  # no key, outage, budget: the agent falls back
        _note(agent, used, UNAVAILABLE)
        raise
    try:
        answer = schema.model_validate_json(_extract_json(raw))
        _note(agent, used, VALID)
        return answer
    except Exception:
        # on schema violation, report the error and retry once (curbs error propagation)
        retry_prompt = (
            "Your previous output failed schema validation. Follow the schema strictly "
            f"and output only JSON.\n\nOriginal request:\n{user}"
        )
        try:
            retry = complete(sys_full, retry_prompt, agent=agent, model=model, temperature=0.0)
            answer = schema.model_validate_json(_extract_json(retry))
        except Exception:
            _note(agent, used, INVALID)
            raise
        _note(agent, used, RETRIED)
        return answer


def _extract_json(text: str) -> str:
    """Extract the first JSON object from code fences / surrounding text."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1]
        if text.startswith("json"):
            text = text[4:]
    start, end = text.find("{"), text.rfind("}")
    return text[start : end + 1] if start != -1 and end != -1 else text
