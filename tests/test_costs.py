"""The cost ledger: tokens as the provider reported them, USD from a versioned price table."""
from __future__ import annotations

import json

import litellm
import pytest
from fastapi.testclient import TestClient
from litellm.llms.anthropic.chat.transformation import AnthropicConfig
from sqlalchemy import delete, select

from ma_pmo.api.main import app
from ma_pmo.core import costs, llm, workspace
from ma_pmo.core.config import get_settings
from ma_pmo.core.scenarios import run_scenario
from ma_pmo.db import workspaces
from ma_pmo.db.models import LlmCall, Workspace
from ma_pmo.db.session import get_session

client = TestClient(app)
MODEL = "anthropic/claude-sonnet-5"

# usage blocks shaped exactly as each provider returns them
ANTHROPIC = [
    {"input_tokens": 1200, "output_tokens": 350,
     "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0},
    {"input_tokens": 120, "output_tokens": 80,
     "cache_creation_input_tokens": 2048, "cache_read_input_tokens": 0},  # writes the cache
    {"input_tokens": 120, "output_tokens": 95,
     "cache_creation_input_tokens": 0, "cache_read_input_tokens": 2048},  # reads it back
]
OPENAI = {"prompt_tokens": 1500, "completion_tokens": 200, "total_tokens": 1700,
          "prompt_tokens_details": {"cached_tokens": 1024}}


def _anthropic_response(raw: dict, model: str = "claude-sonnet-5") -> litellm.ModelResponse:
    usage = AnthropicConfig().calculate_usage(raw, None)  # what LiteLLM makes of the raw block
    response = litellm.ModelResponse(model=model, usage=usage)
    response.choices[0].message.content = "{}"
    response._hidden_params = {"custom_llm_provider": "anthropic"}
    return response


@pytest.fixture(autouse=True)
def empty_ledger():
    with get_session() as s:
        s.execute(delete(LlmCall))
    yield
    with get_session() as s:
        s.execute(delete(LlmCall))


@pytest.mark.parametrize("raw", ANTHROPIC)
def test_tokens_and_usd_match_the_provider_and_litellm(raw):
    response = _anthropic_response(raw)
    usage = costs.usage_of(response)
    # every token the provider reported, nothing more
    assert usage.prompt == (raw["input_tokens"] + raw["cache_creation_input_tokens"]
                            + raw["cache_read_input_tokens"])
    assert (usage.completion, usage.cache_read, usage.cache_write) == (
        raw["output_tokens"], raw["cache_read_input_tokens"], raw["cache_creation_input_tokens"])
    price, table = costs.price_of(MODEL)
    assert price is not None and table.startswith("litellm ")
    expected = litellm.completion_cost(completion_response=response, model="claude-sonnet-5",
                                       custom_llm_provider="anthropic")
    assert costs.usd(usage, price) == pytest.approx(expected, rel=1e-9)


def test_openai_style_cached_tokens_are_priced_as_cache_reads():
    response = litellm.ModelResponse(model="gpt-4o", usage=litellm.Usage(**OPENAI))
    usage = costs.usage_of(response)
    assert (usage.prompt, usage.completion, usage.cache_read, usage.cache_write) == (
        1500, 200, 1024, 0)
    price, _ = costs.price_of("gpt-4o")
    assert price is not None
    assert costs.usd(usage, price) == pytest.approx(
        476 * price.input + 1024 * price.cache_read + 200 * price.output)


def test_an_unknown_model_stays_unpriced_never_guessed():
    price, _ = costs.price_of("acme/made-up-model")
    assert price is None and costs.usd(costs.Usage(100, 10), None) is None
    assert costs.record("acme/made-up-model", "A5", costs.Usage(100, 10), 5.0) is None
    with get_session() as s:
        row = s.scalars(select(LlmCall)).one()
    assert row.usd is None and row.price_version is None and row.prompt_tokens == 100
    total = client.get("/costs").json()["total"]
    assert total["calls"] == 1 and total["usd"] is None and total["unpriced"] == 1


def test_your_own_price_table_wins_and_names_its_version(tmp_path, monkeypatch):
    table = tmp_path / "prices.json"
    table.write_text(json.dumps({"version": "acme-2026-11", "models": {
        MODEL: {"input": 3.0, "output": 15.0, "cache_read": 0.3}}}), encoding="utf-8")
    monkeypatch.setattr(get_settings(), "price_table", str(table))
    price, version = costs.price_of(MODEL)
    assert version == "acme-2026-11" and price is not None
    assert price.cache_write == pytest.approx(3.0 / 1_000_000)  # defaults to input
    cost = costs.usd(costs.Usage(prompt=1_000_000, completion=1_000_000), price)
    assert cost == pytest.approx(18.0)


def test_a_run_records_each_call_with_its_run_step_and_agent(monkeypatch):
    replies = iter(_anthropic_response(r) for r in ANTHROPIC * 20)
    monkeypatch.setattr(llm.litellm, "completion", lambda **kw: next(replies))
    trace = run_scenario("risk_escalation")
    with get_session() as s:
        rows = s.scalars(select(LlmCall).order_by(LlmCall.id)).all()
    assert rows and all(r.run_id == trace["run_id"] for r in rows)
    assert {r.agent for r in rows} <= {"A4", "A5", "A6"} and {r.step_seq for r in rows} <= {1, 2, 3}
    assert all(r.model == get_settings().llm_model and r.usd and r.usd > 0 for r in rows)

    by_step = client.get(f"/runs/{trace['run_id']}/costs").json()
    assert by_step["total"]["calls"] == len(rows)
    assert by_step["total"]["usd"] == pytest.approx(sum(r.usd for r in rows), abs=1e-6)
    assert by_step["total"]["prompt_tokens"] == sum(r.prompt_tokens for r in rows)
    by_agent = client.get("/costs", params={"by": "agent"}).json()
    assert sum(r["calls"] for r in by_agent["rows"]) == len(rows)
    by_workflow = client.get("/costs", params={"by": "workflow", "days": 1}).json()
    assert by_workflow["rows"][0]["key"] == "risk_escalation"
    assert client.get("/costs", params={"by": "step"}).status_code == 422
    assert client.get("/runs/nope/costs").status_code == 404


def test_a_ledger_failure_never_breaks_the_call(monkeypatch):
    monkeypatch.setattr(costs, "price_of", lambda model: 1 / 0)
    assert costs.record(MODEL, "A5", costs.Usage(1, 1), 1.0) is None


def test_each_workspace_sees_only_its_own_costs():
    workspaces.create("acme-costs", "Acme")
    try:
        with workspace.use("acme-costs"):
            costs.record(MODEL, "A5", costs.Usage(1000, 100), 1.0)
        costs.record(MODEL, "A4", costs.Usage(10, 1), 1.0)
        mine = client.get("/costs", params={"by": "agent"}).json()
        there = client.get("/costs", params={"by": "agent"},
                           headers={workspace.HEADER: "acme-costs"}).json()
        assert [r["key"] for r in mine["rows"]] == ["A4"]
        assert [r["key"] for r in there["rows"]] == ["A5"]
    finally:
        with workspace.use("acme-costs"), get_session() as s:
            s.execute(delete(LlmCall))
        with get_session() as s:
            s.execute(delete(Workspace).where(Workspace.id == "acme-costs"))
