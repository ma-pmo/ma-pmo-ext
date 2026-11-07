"""The one executor: runs a WorkflowSpec as a LangGraph graph.

Every run goes through here, whether it came from a scenario or from a goal routed by A1. A step
starts when the steps it `needs` are done, so independent steps run in parallel and a step with
several prerequisites waits for all of them.

`run_step` rows are the source of truth, not graph state. That is what makes a run resumable: a
step already finished is skipped, and its saved outputs are read back in workflow order. With
`pause_on_gate`, once a step has queued an approval the steps after it do nothing, and the run
is left `waiting_approval`; steps already running in parallel finish first.
"""
from __future__ import annotations

import operator
import time
from dataclasses import dataclass
from typing import Annotated, Any, TypedDict, cast

from langgraph.graph import END, START, StateGraph

from ma_pmo.agents import registry
from ma_pmo.agents.orchestrator_rules import _headline
from ma_pmo.agents.registry import WORKERS
from ma_pmo.core import runs, tracing
from ma_pmo.core.i18n import tr
from ma_pmo.core.obs import get_logger
from ma_pmo.core.state.blackboard import PortfolioState
from ma_pmo.core.state.checkpointer import shared_checkpointer
from ma_pmo.core.workflow import WorkflowSpec, WorkflowStep

_log = get_logger("executor")


class _GraphState(TypedDict, total=False):
    visited: Annotated[list[str], operator.add]


@dataclass
class Outcome:
    outputs: list[dict]  # in workflow order
    phases: list[dict]  # one execute phase per finished step, in workflow order
    paused: bool


def _phase(agent_id: str, elapsed_ms: float, outputs: list[dict]) -> dict:
    name = registry.title(agent_id)
    return {
        "phase": "execute",
        "agent": agent_id,
        "function": name,
        "title": tr(f"Execute — {agent_id} {name}", f"수행 — {agent_id} {name}"),
        "elapsed_ms": elapsed_ms,
        "results": [
            {"schema": o.get("schema"), "headline": _headline(o.get("schema"), o.get("data") or {})}
            for o in outputs
        ],
    }


def _run_step(step: WorkflowStep, seq: int, workflow: str, scope: str, goal: str) -> None:
    agent_id = step.agent
    state = cast(PortfolioState, {"task_ref": scope, "goal": goal, **step.params})
    _log.info("execute_start", agent=agent_id, function=registry.title(agent_id))
    started = time.perf_counter()
    with tracing.span(f"invoke_agent {agent_id}", {
        tracing.OPERATION: "invoke_agent", tracing.AGENT_ID: agent_id,
        tracing.AGENT_NAME: registry.title(agent_id), tracing.SCENARIO: workflow,
    }), runs.step(agent_id, seq) as handle:
        outputs = WORKERS[agent_id].run(state).get("outputs", [])
        schemas = [o.get("schema") for o in outputs]
        tracing.set_attributes({tracing.OUTPUT_SCHEMAS: schemas})
        elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
        handle.output_schemas = schemas
        handle.result = {"outputs": outputs, "phase": _phase(agent_id, elapsed_ms, outputs)}
    _log.info("execute_done", agent=agent_id, elapsed_ms=elapsed_ms, outputs=schemas)


def _compile(spec: WorkflowSpec, run_id: str, scope: str, goal: str, finished: set[int],
             pause_on_gate: bool, checkpointer: Any) -> Any:
    def node(step: WorkflowStep, seq: int) -> Any:
        def run(_state: _GraphState) -> dict:
            waiting = pause_on_gate and bool(runs.pending_approvals(run_id))
            if seq not in finished and not waiting:
                _run_step(step, seq, spec.id, scope, goal)
            return {"visited": [step.id]}

        return run

    graph: Any = StateGraph(_GraphState)
    for seq, step in enumerate(spec.steps, start=1):
        graph.add_node(step.id, node(step, seq))
    deps = spec.dependencies()
    needed = {need for needs in deps.values() for need in needs}
    for step_id, needs in deps.items():
        if needs:
            graph.add_edge(needs if len(needs) > 1 else needs[0], step_id)
        else:
            graph.add_edge(START, step_id)
        if step_id not in needed:
            graph.add_edge(step_id, END)
    return graph.compile(checkpointer=checkpointer)


def execute(run_id: str, spec: WorkflowSpec, scope: str, goal: str, *,
            pause_on_gate: bool = False, thread_id: str | None = None) -> Outcome:
    """Run the unfinished steps of `spec` in the current run. Agent errors propagate."""
    if not spec.steps:  # an ablation can remove every agent of a workflow
        return Outcome([], [], False)
    finished = set(runs.finished_steps(run_id))
    graph = _compile(spec, run_id, scope, goal, finished, pause_on_gate,
                     shared_checkpointer() if thread_id else None)
    config: dict[str, Any] = {"recursion_limit": len(spec.steps) + 10}
    if thread_id:
        config["configurable"] = {"thread_id": thread_id}
    graph.invoke({"visited": []}, config=config)

    results = runs.finished_steps(run_id)
    outputs: list[dict] = []
    phases: list[dict] = []
    for seq in sorted(results):
        outputs += results[seq].get("outputs", [])
        phases.append(results[seq]["phase"])
    paused = pause_on_gate and bool(runs.pending_approvals(run_id))
    if paused:
        runs.mark_waiting(run_id)
        _log.info("run_waiting", workflow=spec.id, run_id=run_id)
    return Outcome(outputs, phases, paused)


def resume_run(run_id: str) -> dict:
    """Continue a paused or interrupted run: finished steps are reused, the rest run now.

    Raises KeyError for an unknown run and runs.NotResumable if it cannot continue.
    """
    from ma_pmo.core import goals, scenarios

    run = runs.claim(run_id)
    finish = scenarios.finish_scenario if run["kind"] == "scenario" else goals.finish_goal
    with tracing.span(f"invoke_workflow {run['workflow'][:60]}", {
        tracing.OPERATION: "invoke_workflow", tracing.SCOPE: run["scope"], "ma_pmo.resumed": True,
    }), runs.attach(run_id):
        return finish(run_id, run["scope"])
