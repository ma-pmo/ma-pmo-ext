"""Agent plugins, with entry points faked; CI also installs examples/agent-plugin for real."""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel

from ma_pmo.agents import registry
from ma_pmo.agents.orchestrator import OrchestratorAgent
from ma_pmo.agents.orchestrator_rules import keyword_route
from ma_pmo.api.main import app
from ma_pmo.core import hitl
from ma_pmo.core.goals import run_goal
from ma_pmo.core.schemas.payloads import PAYLOAD_REGISTRY
from ma_pmo.sdk import BaseAgent, publish
from ma_pmo.sdk.testing import assert_agent_contract


class NoteV1(BaseModel):
    text: str


class NoteAgent(BaseAgent[NoteV1]):
    agent_id = "acme.note"
    function = "Note"
    output_schema = NoteV1

    def run(self, state):
        note = NoteV1(text="hello")
        return {"outputs": [publish(self, "acme_note.v1", note, task_ref=state["task_ref"],
                                    needs_approval=state.get("approve", False))]}


def _spec(**changes) -> registry.AgentSpec:
    values = dict(id="acme.note", name=("Note", "메모"), version="1.2.0",
                  capability="Note (test agent): note", keywords=("memo-word",),
                  default_task=("Write a note", "메모 작성"), output_schema="acme_note.v1",
                  factory=NoteAgent, payload=NoteV1)
    return registry.AgentSpec(**{**values, **changes})


def _entry_point(name: str, value) -> SimpleNamespace:
    def load():
        if isinstance(value, Exception):
            raise value
        return value

    return SimpleNamespace(name=name, load=load, dist=SimpleNamespace(name=f"pkg-{name}"))


@pytest.fixture
def install(monkeypatch):
    def _install(*eps):
        monkeypatch.setattr(registry, "entry_points", lambda group: list(eps))
        registry.reload_plugins()

    yield _install
    monkeypatch.undo()
    registry.reload_plugins()


@pytest.mark.smoke
def test_plugin_joins_routing_prompt_and_payload_validation(install):
    install(_entry_point("note", _spec()))
    spec = registry.specs()["acme.note"]
    assert spec.source == "pkg-note" and registry.problems() == []
    builtins = [b.id for b in registry.BUILTINS]
    assert list(registry.specs())[:len(builtins)] == builtins  # built-ins first
    assert [d.agent for d in keyword_route("a memo-word please").delegations] == ["acme.note"]
    assert "acme.note Note (test agent)" in OrchestratorAgent().role_prompt
    assert PAYLOAD_REGISTRY["acme_note.v1"] is NoteV1


def test_plugin_runs_for_a_goal(install):
    install(_entry_point("note", _spec()))
    final = run_goal("memo-word", "PORTFOLIO#2026-Q1")
    assert [o["agent"] for o in final["outputs"]] == ["acme.note"]


@pytest.mark.parametrize("value, reason", [
    (RuntimeError("no such module"), "RuntimeError"),
    ("not a spec", "not an AgentSpec"),
    (_spec(id="A9"), "vendor.name"),
    (_spec(id="A2"), "vendor.name"),
    (_spec(payload=None), "payload model"),
    (_spec(output_schema="note"), "must include a version"),
    (_spec(output_schema="schedule.v1"), "built-in"),
])
def test_bad_plugin_is_reported_and_skipped(install, value, reason):
    install(_entry_point("bad", value), _entry_point("good", _spec()))
    assert "acme.note" in registry.specs()
    assert len(registry.specs()) == len(registry.BUILTINS) + 1
    (problem,) = registry.problems()
    assert problem.startswith("bad:") and reason in problem


def test_two_plugins_cannot_share_an_id(install):
    install(_entry_point("one", _spec()), _entry_point("two", _spec()))
    assert registry.specs()["acme.note"].source == "pkg-one"
    assert "already used by pkg-one" in registry.problems()[0]


def test_contract_kit_passes_and_fails_with_a_reason(install):
    install(_entry_point("note", _spec()))
    assert assert_agent_contract(_spec())["outputs"][0]["data"] == {"text": "hello"}

    class Silent(NoteAgent):
        def run(self, state):
            return {"outputs": []}

    with pytest.raises(AssertionError, match="ma_pmo.sdk.publish"):
        assert_agent_contract(_spec(factory=Silent))

    class Wrong(NoteAgent):
        agent_id = "acme.other"

    with pytest.raises(AssertionError, match="differs from spec"):
        assert_agent_contract(_spec(factory=Wrong))


def test_sdk_publish_uses_the_approval_gate(install):
    install(_entry_point("note", _spec()))
    assert_agent_contract(_spec(), {"approve": True})
    assert any(a["sender"] == "acme.note" for a in hitl.list_pending())


def test_invalid_output_is_rejected_by_the_protocol(install):
    install(_entry_point("note", _spec()))
    registry.specs()  # plugins load on first lookup, which is how an agent is reached

    class Other(BaseModel):
        number: int

    with pytest.raises(ValueError):
        publish(NoteAgent(), "acme_note.v1", Other(number=1), task_ref="T")


def test_listing_through_api_and_cli(install, capsys):
    from ma_pmo.cli import _cmd_agents

    install(_entry_point("note", _spec()), _entry_point("bad", RuntimeError("boom")))
    body = TestClient(app).get("/agents").json()
    assert {"id": "acme.note", "source": "pkg-note"}.items() <= body["agents"][-1].items()
    assert "boom" in body["problems"][0]
    assert _cmd_agents() == 1
    out = capsys.readouterr().out
    assert "acme.note" in out and "pkg-note" in out and "boom" in out
