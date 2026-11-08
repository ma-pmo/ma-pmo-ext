"""Tracing: a scenario run becomes one trace with agent and LLM spans, and fallbacks are marked.

Skipped when the optional `otel` extra is not installed (CI installs it).
"""
from __future__ import annotations

import pytest

pytest.importorskip("opentelemetry.sdk")

from opentelemetry.sdk.trace.export.in_memory_span_exporter import (  # noqa: E402
    InMemorySpanExporter,
)

from ma_pmo.core import tracing  # noqa: E402
from ma_pmo.core.config import Settings  # noqa: E402
from ma_pmo.core.scenarios import run_scenario  # noqa: E402


@pytest.fixture
def spans():
    exporter = InMemorySpanExporter()
    assert tracing.configure_tracing(exporter=exporter) == "custom"
    yield exporter
    tracing._tracer = None  # back to no-op for the other tests


def test_off_by_default_is_a_no_op():
    tracing._tracer = None
    assert tracing.configure_tracing(Settings(OTEL_ENABLED=False)) == "off"
    with tracing.span("anything", {"a": 1}) as current:
        assert current is None
    tracing.set_attributes({"a": 1})
    tracing.mark_fallback("x")


@pytest.mark.smoke
def test_scenario_run_is_one_trace(spans):
    run_scenario("quarterly_review")
    finished = spans.get_finished_spans()
    by_name = {s.name: s for s in finished}
    root = by_name["invoke_workflow quarterly_review"]
    agents = [s for s in finished if s.name.startswith("invoke_agent ")]
    assert {s.name for s in agents} == {"invoke_agent A2", "invoke_agent A4", "invoke_agent A5",
                                        "invoke_agent A8"}
    assert all(s.context.trace_id == root.context.trace_id for s in finished)
    assert all(s.parent is not None and s.parent.span_id == root.context.span_id for s in agents)
    a2 = by_name["invoke_agent A2"]
    assert a2.attributes[tracing.OPERATION] == "invoke_agent"
    assert "schedule.v1" in a2.attributes[tracing.OUTPUT_SCHEMAS]


def test_llm_failure_and_fallback_are_visible(spans):
    # tests run without an LLM, so A5's report call fails and falls back to the rules
    run_scenario("weekly_status")
    finished = spans.get_finished_spans()
    chats = [s for s in finished if s.name.startswith("chat ")]
    assert chats and chats[0].attributes[tracing.OPERATION] == "chat"
    assert not chats[0].status.is_ok  # the failed call is recorded as an error
    a5 = next(s for s in finished if s.name == "invoke_agent A5")
    assert a5.attributes[tracing.FALLBACK] is True
    assert any(e.name == "fallback" for e in a5.events)
