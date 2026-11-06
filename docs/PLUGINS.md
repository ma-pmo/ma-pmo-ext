# Agent plugins

**English | [한국어](PLUGINS.ko.md)**

Add a worker agent to MA-PMO from your own package, without changing MA-PMO. The orchestrator
routes goals to it, its output goes through the audited message log, and risky results wait for
a person like those of any built-in agent. A complete example lives in
[examples/agent-plugin](../examples/agent-plugin/README.md).

## Write one

```python
from pydantic import BaseModel
from ma_pmo.sdk import AgentSpec, BaseAgent, get_tracker, publish

class BudgetV1(BaseModel):            # the payload contract
    project_id: str
    remaining_cost: float

class BudgetAgent(BaseAgent[BudgetV1]):
    agent_id = "acme.budget"
    function = "Budget"
    output_schema = BudgetV1

    def run(self, state):
        scope = state.get("task_ref", "PORTFOLIO#2026-Q1")
        outputs = []
        for project in get_tracker().get_portfolio_status(scope)["projects"]:
            budget = BudgetV1(project_id=project["project_id"], remaining_cost=...)
            outputs.append(publish(self, "acme_budget.v1", budget, task_ref=scope))
        return {"outputs": outputs}

SPEC = AgentSpec(
    id="acme.budget", name=("Budget", "예산"), version="0.1.0",
    capability="Budget (cost of remaining work): budget, cost, spend",
    keywords=("budget", "cost", "예산", "비용"),
    default_task=("Estimate the cost of remaining work", "남은 작업 비용 추정"),
    output_schema="acme_budget.v1", factory=BudgetAgent, payload=BudgetV1,
)
```

Register it in your `pyproject.toml`, install the package next to MA-PMO, and it is there:

```toml
[project.entry-points."ma_pmo.agents"]
budget = "my_package:SPEC"
```

```bash
ma-pmo agents        # id, name, version, source; exits 1 if a plugin could not load
```

`GET /agents` shows the same list.

## Rules

| Rule | Why |
|---|---|
| Id is `vendor.name`, lowercase | Plugins cannot collide with or replace `A1`–`A7` |
| Declare `payload`, and a versioned `output_schema` of your own | Output is validated like any built-in agent's |
| Publish with `ma_pmo.sdk.publish` | Output reaches the audit log and the approval gate |
| Set `needs_approval=True` for high-impact results | A person decides; low confidence also goes to the queue |
| Import only from `ma_pmo.sdk` | It is the only stable surface; breaking it raises `SDK_VERSION` |

`capability` is the line the orchestrator's LLM reads and `keywords` drive routing without an
LLM, so write both for the goals you want to catch. A plugin that fails to load is reported by
`ma-pmo agents` and skipped; MA-PMO keeps running.

## Test it

```python
from ma_pmo.sdk.testing import assert_agent_contract
from my_package import SPEC

def test_contract():
    assert_agent_contract(SPEC)   # builds the agent, runs it, validates its output
```

It needs a database with the demo portfolio; see the example's `conftest.py`.

## Trust

A plugin is ordinary Python running inside the MA-PMO process, with its database access, its
environment variables and its API keys. There is no sandbox, and the approval gate relies on
the plugin asking for it. Install plugins the way you would install any dependency: only from
sources you trust, and pinned.
