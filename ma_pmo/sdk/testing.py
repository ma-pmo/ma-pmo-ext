"""Contract check for agent plugins: call it from the plugin's own tests."""
from __future__ import annotations

from ma_pmo.agents.registry import AgentSpec, _check_plugin
from ma_pmo.core.scope import DEFAULT_SCOPE

DEFAULT_STATE = {"task_ref": DEFAULT_SCOPE, "goal": "contract check"}


def assert_agent_contract(spec: AgentSpec, state: dict | None = None) -> dict:
    """Build the agent, run it once and check what MA-PMO relies on. Returns the result.

    Needs a database with data for the portfolio in `state` (`ma-pmo init-db` for the demo).
    """
    problem = _check_plugin(spec)
    assert problem is None, problem
    assert spec.capability.strip(), "capability tells the orchestrator when to route here"
    agent = spec.factory()
    assert agent.agent_id == spec.id, f"agent_id {agent.agent_id!r} differs from spec {spec.id!r}"
    result = agent.run({**DEFAULT_STATE, **(state or {})})  # type: ignore[typeddict-item]
    outputs = result.get("outputs")
    assert outputs, "run() must return {'outputs': [...]}; use ma_pmo.sdk.publish"
    assert spec.payload is not None
    for output in outputs:
        assert output.get("agent") == spec.id, f"output agent is {output.get('agent')!r}"
        assert output.get("schema") == spec.output_schema, f"schema is {output.get('schema')!r}"
        spec.payload.model_validate(output.get("data"))
    return result
