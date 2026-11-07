"""Per-step model tiers and prompt caching."""
from __future__ import annotations

import litellm
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from ma_pmo.api.main import app
from ma_pmo.core import llm, scenarios, workflow_store
from ma_pmo.core.config import get_settings
from ma_pmo.core.scenarios import run_scenario, run_spec
from ma_pmo.core.workflow import WorkflowSpec
from ma_pmo.db.models import LlmCall, WorkflowVersion
from ma_pmo.db.session import get_session

client = TestClient(app)
STANDARD, FAST = get_settings().llm_model, get_settings().llm_model_fast


@pytest.fixture(autouse=True)
def clean():
    yield
    with get_session() as s:
        s.execute(delete(LlmCall))
        s.execute(delete(WorkflowVersion))


@pytest.fixture
def sent(monkeypatch) -> list[dict]:
    """What would have gone to the provider."""
    requests: list[dict] = []

    def completion(**kw):
        requests.append(kw)
        response = litellm.ModelResponse(model=kw["model"])
        response.choices[0].message.content = "{}"
        return response

    monkeypatch.setattr(llm.litellm, "completion", completion)
    return requests


def _briefing(tiers: dict[str, str]) -> WorkflowSpec:
    """executive_briefing (A2 -> A3 -> A4 -> A5; A4 and A5 call the LLM) with tiers set."""
    spec = scenarios.loaded("executive_briefing")
    steps = [s.model_copy(update={"model_tier": tiers.get(s.id)}) for s in spec.steps]
    return spec.model_copy(update={"steps": steps})


def test_steps_use_the_model_of_their_tier(sent):
    spec = _briefing({"A4": "fast"})
    run_spec(spec)
    with get_session() as s:
        used = {(r.agent, r.model) for r in s.scalars(select(LlmCall))}
    assert ("A4", FAST) in used and ("A5", STANDARD) in used
    assert ("A4", STANDARD) not in used and ("A5", FAST) not in used
    assert {r["model"] for r in sent} == {FAST, STANDARD}
    by_model = {r["key"] for r in client.get("/costs").json()["rows"]}
    assert by_model == {FAST, STANDARD}


def test_without_a_tier_everything_stays_on_the_standard_model(sent):
    run_scenario("executive_briefing")
    assert sent and {r["model"] for r in sent} == {STANDARD}


def test_calls_outside_a_step_and_after_it_use_the_standard_model(sent):
    with llm.use_tier("fast"):
        assert llm.model_for() == FAST
    assert llm.model_for() == STANDARD and llm.model_for("fast") == FAST


def test_an_empty_fast_model_falls_back_to_the_standard_one(monkeypatch):
    monkeypatch.setattr(get_settings(), "llm_model_fast", "")
    assert llm.model_for("fast") == STANDARD


def test_the_system_prompt_is_cacheable_on_anthropic_only(sent, monkeypatch):
    llm.complete("You are A5.", "Report.", model="anthropic/claude-sonnet-5")
    system = sent[-1]["messages"][0]["content"]
    assert system[0]["cache_control"] == {"type": "ephemeral"}
    assert system[0]["text"].startswith("You are A5.")
    llm.complete("You are A5.", "Report.", model="ollama_chat/llama3.1:8b")
    assert isinstance(sent[-1]["messages"][0]["content"], str)
    monkeypatch.setattr(get_settings(), "llm_prompt_cache", False)
    llm.complete("You are A5.", "Report.", model="anthropic/claude-sonnet-5")
    assert isinstance(sent[-1]["messages"][0]["content"], str)


def test_the_api_shows_tiers_and_what_they_mean():
    listed = client.get("/workflows").json()
    assert listed["models"] == {"standard": STANDARD, "fast": FAST}
    steps = client.get("/workflows/executive_briefing").json()["steps"]
    assert {s["model_tier"] for s in steps} == {"standard"}


def test_a_tier_is_validated_saved_published_and_used(sent):
    spec = _briefing({"A5": "fast"}).model_dump()
    assert client.post("/workflows/validate", json={"spec": spec}).json()["ok"] is True
    bad = _briefing({}).model_dump()
    bad["steps"][0]["model_tier"] = "turbo"
    problems = client.post("/workflows/validate", json={"spec": bad}).json()["problems"]
    assert problems and "model_tier" in problems[0]

    version = workflow_store.save_draft(spec, "test")["version"]
    workflow_store.publish("executive_briefing", version, "test")
    steps = client.get("/workflows/executive_briefing").json()["steps"]
    assert {s["id"]: s["model_tier"] for s in steps}["A5"] == "fast"
    run_scenario("executive_briefing")
    with get_session() as s:
        a5 = {r.model for r in s.scalars(select(LlmCall).where(LlmCall.agent == "A5"))}
    assert a5 == {FAST}
