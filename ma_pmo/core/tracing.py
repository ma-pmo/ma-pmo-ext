"""OpenTelemetry tracing for agent runs — optional, off by default.

    pip install "ma-pmo[otel]"
    OTEL_ENABLED=true                                   # spans to stderr (console)
    OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318   # or: send to a collector / Jaeger

A scenario run becomes one trace: `invoke_workflow <scenario>` → `invoke_agent <A2…A7>` →
`chat <model>` for each LLM call. When an agent falls back to its deterministic path, the span
gets `ma_pmo.fallback=true` and a `fallback` event, so outages show up in the trace instead of
only in quality.

Attribute names follow the OpenTelemetry GenAI semantic conventions where they exist. Those
conventions are still evolving upstream, so every name lives in this module — rename here,
nowhere else. Without the extra or with tracing off, every helper is a cheap no-op.
"""
from __future__ import annotations

import os
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from ma_pmo.core.config import Settings, get_settings

# GenAI semantic conventions (gen_ai.*) and MA-PMO's own attributes (ma_pmo.*)
OPERATION = "gen_ai.operation.name"
AGENT_ID = "gen_ai.agent.id"
AGENT_NAME = "gen_ai.agent.name"
REQUEST_MODEL = "gen_ai.request.model"
INPUT_TOKENS = "gen_ai.usage.input_tokens"
OUTPUT_TOKENS = "gen_ai.usage.output_tokens"
SCENARIO = "ma_pmo.scenario.id"
SCOPE = "ma_pmo.scope"
OUTPUT_SCHEMAS = "ma_pmo.output.schemas"
FALLBACK = "ma_pmo.fallback"
FALLBACK_COMPONENT = "ma_pmo.fallback.component"

_tracer: Any = None
_global_mode: str | None = None  # the global provider can be set only once per process


def configure_tracing(settings: Settings | None = None, *, exporter: Any = None) -> str:
    """Set up tracing once at startup. Returns the mode: "off", "console", "otlp" or "custom".

    `exporter` (tests, or your own exporter) bypasses the environment and the global provider.
    """
    global _tracer, _global_mode
    if exporter is None and _global_mode is not None:
        return _global_mode  # `ma-pmo serve` configures in the CLI, then again on API import
    settings = settings or get_settings()
    if exporter is None and not settings.otel_enabled:
        _tracer = None
        return "off"
    try:
        from opentelemetry import trace
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import (
            BatchSpanProcessor,
            ConsoleSpanExporter,
            SimpleSpanProcessor,
        )
    except ImportError:
        print('tracing needs the extra: pip install "ma-pmo[otel]" (continuing without it)',
              file=sys.stderr)
        _tracer = None
        return "off"

    from ma_pmo import __version__

    resource = Resource.create({"service.name": settings.otel_service_name,
                                "service.version": __version__})
    provider = TracerProvider(resource=resource)
    if exporter is not None:
        provider.add_span_processor(SimpleSpanProcessor(exporter))
        _tracer = provider.get_tracer("ma_pmo")
        return "custom"
    if os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT") or os.environ.get(
            "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT"):
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
        mode = "otlp"
    else:
        # stderr, never stdout: stdout carries the MCP protocol when running `ma-pmo mcp`
        provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter(out=sys.stderr)))
        mode = "console"
    trace.set_tracer_provider(provider)
    _tracer = trace.get_tracer("ma_pmo")
    _global_mode = mode
    return mode


def _clean(attributes: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in attributes.items():
        if value is None:
            continue
        if isinstance(value, (list, tuple)):
            value = [str(v) for v in value]
        elif not isinstance(value, (str, bool, int, float)):
            value = str(value)
        out[key] = value
    return out


@contextmanager
def span(name: str, attributes: dict[str, Any] | None = None) -> Iterator[Any]:
    """A child span of the current one. Exceptions are recorded and re-raised."""
    if _tracer is None:
        yield None
        return
    with _tracer.start_as_current_span(name, attributes=_clean(attributes or {})) as current:
        yield current


def current_trace_id() -> str | None:
    """Hex id of the active trace, to link a run record to its trace."""
    if _tracer is None:
        return None
    from opentelemetry import trace

    context = trace.get_current_span().get_span_context()
    return format(context.trace_id, "032x") if context.is_valid else None


def set_attributes(attributes: dict[str, Any]) -> None:
    """Add attributes to the current span (no-op when tracing is off)."""
    if _tracer is None:
        return
    from opentelemetry import trace

    trace.get_current_span().set_attributes(_clean(attributes))


def mark_fallback(component: str, error: BaseException | None = None) -> None:
    """Record on the current span that `component` used its deterministic fallback."""
    if _tracer is None:
        return
    from opentelemetry import trace

    current = trace.get_current_span()
    current.set_attributes({FALLBACK: True, FALLBACK_COMPONENT: component})
    event: dict[str, Any] = {FALLBACK_COMPONENT: component}
    if error is not None:
        event["exception.type"] = type(error).__name__
        event["exception.message"] = str(error)[:300]
    current.add_event("fallback", event)
