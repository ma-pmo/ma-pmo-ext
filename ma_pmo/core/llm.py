"""LLM gateway — provider abstraction (LiteLLM), Anthropic Claude by default.

- swappable model (LLM_MODEL env)
- token and latency usage reported as KPIs (cost axis)
- structured output: enforced Pydantic schema (JSON mode) — curbs hallucination/format errors
- natural-language output follows the active language (core/i18n.py)
"""
from __future__ import annotations

import json
import time
from typing import TypeVar

import litellm
from pydantic import BaseModel

from ma_pmo.core import kpi
from ma_pmo.core.config import get_settings
from ma_pmo.core.i18n import get_lang

_settings = get_settings()
T = TypeVar("T", bound=BaseModel)

# LiteLLM global settings
litellm.drop_params = True  # drop unsupported params automatically (provider portability)


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
    """Free-form completion. Usage is recorded on the KPI cost axis."""
    model = model or _settings.llm_model
    language = "Korean" if get_lang() == "ko" else "English"
    system = f"{system}\n\nWrite all natural-language text in {language}."
    t0 = time.monotonic()
    resp = litellm.completion(
        model=model,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        temperature=_settings.llm_temperature if temperature is None else temperature,
        max_tokens=max_tokens or _settings.llm_max_tokens,
        **_provider_kwargs(model),
    )
    latency_ms = (time.monotonic() - t0) * 1000
    usage = getattr(resp, "usage", None)
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
    raw = complete(sys_full, user, agent=agent, model=model, temperature=0.0)
    try:
        return schema.model_validate_json(_extract_json(raw))
    except Exception:
        # on schema violation, report the error and retry once (curbs error propagation)
        retry_prompt = (
            "Your previous output failed schema validation. Follow the schema strictly "
            f"and output only JSON.\n\nOriginal request:\n{user}"
        )
        retry = complete(
            sys_full,
            retry_prompt,
            agent=agent,
            model=model,
            temperature=0.0,
        )
        return schema.model_validate_json(_extract_json(retry))


def _extract_json(text: str) -> str:
    """Extract the first JSON object from code fences / surrounding text."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1]
        if text.startswith("json"):
            text = text[4:]
    start, end = text.find("{"), text.rfind("}")
    return text[start : end + 1] if start != -1 and end != -1 else text
