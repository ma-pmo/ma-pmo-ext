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

## Use it in a workflow

Workflows are JSON. Put a file in the folder `MA_PMO_WORKFLOWS_DIR` (default `./workflows`) and it
runs like a built-in scenario, with `POST /scenarios/budget_review/run`:

```json
{
  "id": "budget_review",
  "title": {"en": "Budget review", "ko": "예산 점검"},
  "goal": {"en": "Review the cost of remaining work", "ko": "남은 작업 비용 점검"},
  "description": {"en": "Estimate remaining cost, then report.", "ko": "남은 비용을 추정하고 보고한다."},
  "steps": [
    {"id": "budget", "agent": "acme.budget"},
    {"id": "report", "agent": "A5"}
  ]
}
```

A step follows the one before it unless it lists `needs`, and takes optional `params`. Files are
read at startup. An invalid file, an unknown agent or an id already in use is reported under
`workflow_problems` in `GET /agents`, and the file is skipped.

### What a step may read

A step's agent works from its own data and does not see what other steps published, unless the
workflow allows it with `reads`:

| `reads` | The step sees |
|---|---|
| `isolated` (default) | nothing from other steps; its state has no `board` |
| `upstream` | the posts of every step it waits for, directly or through others |
| `board` | the posts of every step in an earlier stage |

```json
{"id": "report", "agent": "A5", "needs": ["risk"], "reads": "upstream"}
```

The agent reads them with `ma_pmo.sdk.board_posts(state, schema=None)`. Each post carries the
`message_id`, `step`, `agent`, `schema`, `data`, `confidence` and `evidence` of a published
message. When an output rests on posts or data, say so with
`publish(..., evidence=[EvidenceRef(kind="message", ref=post["message_id"])])`; the other kinds
are `tracker` (with `field`) and `knowledge`. `GET /runs/{id}/board` shows every post of a run
and what each step could read. The modes follow the gated bulletin board of ArcticSwarm (Yoon et
al., 2026, arXiv:2609.01870): publishing is always allowed, reading is granted per step.

To check the result, open **Workflows** in the dashboard: each workflow is drawn as stages that
can run in parallel, with the same steps as a table and required steps (such as gates) marked.
`GET /workflows` and `GET /workflows/{id}` return the same, including each step's resolved
`needs` and `level`.

Pick a run above the graph (or follow **See it on the workflow** after running a scenario) to see
where each step of that run stands: done, running, awaiting approval, failed or not started. The
graph is the workflow exactly as that run saved it, and it updates while the run is going.
`GET /runs/{id}/workflow` returns the same; `GET /runs?workflow=<id>` lists a workflow's runs.

### Versions: draft, then publish

A workspace can change a workflow without touching files. In the dashboard, **Edit** on a
workflow opens a form: add, remove and reorder steps, tick what each step waits for, and set its
parameters (`key=value, key=value`). Every change is checked by the server as you type, and a
live graph shows the result. Required steps of the version in use are locked. **Dry run on demo
data** runs the draft in a throwaway workspace on the sample portfolio: no real data, approval or
notification is touched (trackers read the demo data even if Jira is configured), and the
workspace is erased afterwards; agents still call the LLM if one is configured. Editing needs a
wide screen; on a phone workflows are read-only.
 Saving creates a new **draft version**
(its spec never changes again); an `approver` or `admin` **publishes** it, and from then on it is
the version that runs in that workspace. Every version stays readable, and every run keeps the
version it started with (shown in the run menu and `workflow_version` in `GET /runs`).

One validator runs for the API, the CLI and the dashboard. Beyond the spec's own rules (unique
steps, known `needs`, no cycles) it rejects unknown agents and categories, a gate step that is
not `required`, and **removing or changing a required step** of the version in use. Publishing
checks again, in case another version was published in between.

```bash
ma-pmo workflow validate my_flow.json          # the problems, if any; saves nothing
ma-pmo workflow draft my_flow.json --note "why" # a new draft version
ma-pmo workflow versions knowledge_kickoff      # * marks the version in use
ma-pmo workflow publish knowledge_kickoff 2
```

The API is the same: `POST /workflows/validate`, `POST /workflows/dry-run`,
`POST /workflows/{id}/versions`,
`POST /workflows/{id}/versions/{v}/publish`, `GET /workflows/{id}/versions[/{v}]`. A rejected
draft answers 422 with `detail.problems`.

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
