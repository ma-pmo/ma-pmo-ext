"""Goals: A1 turns a goal into a workflow, the executor runs it, A1 synthesizes the outputs.

A1 -> delegated workers (in parallel) -> A1. The routing decision becomes an ordinary
WorkflowSpec, so a goal gets the same run records, approval pause and recovery as a scenario.
"""
from __future__ import annotations

import uuid

from ma_pmo.agents.orchestrator import OrchestratorAgent
from ma_pmo.core import executor, runs, tracing
from ma_pmo.core.workflow import Text, WorkflowSpec, WorkflowStep


def workflow_for(goal: str, routing: dict) -> WorkflowSpec:
    """The delegated workers as parallel steps: A1 asked for them independently."""
    steps: list[WorkflowStep] = []
    for delegation in routing.get("delegations", []):
        agent = delegation["agent"]
        if all(s.agent != agent for s in steps):
            steps.append(WorkflowStep(id=agent, agent=agent, needs=[],
                                      params={"task": delegation.get("task", "")}))
    text = Text(en=goal or "-", ko=goal or "-")
    # goals are not reviewed yet: their steps run side by side, with no decision to commit
    return WorkflowSpec(id="goal", title=text, goal=text, description=text, steps=steps,
                        review=False)


def run_goal(goal: str, task_ref: str, *, thread_id: str | None = None,
             pause_on_gate: bool = False) -> dict:
    thread_id = thread_id or f"thread-{uuid.uuid4().hex[:8]}"
    state = {"goal": goal, "pause_on_gate": pause_on_gate}
    with tracing.span("invoke_workflow goal", {
        tracing.OPERATION: "invoke_workflow", tracing.SCOPE: task_ref,
    }), runs.track("orchestrate", goal, task_ref, thread_id=thread_id, state=state) as run_id:
        routing = OrchestratorAgent().route({"goal": goal, "task_ref": task_ref})["routing"]
        runs.update_state(run_id, routing=routing,
                          spec=workflow_for(goal, routing).model_dump())
        return finish_goal(run_id, task_ref)


def finish_goal(run_id: str, scope: str) -> dict:
    """Run what is left of a goal's workflow, then synthesize. Also how a goal resumes."""
    saved = runs.get_state(run_id)
    spec = WorkflowSpec.model_validate(saved["spec"])
    thread_id = (runs.get_run(run_id) or {}).get("thread_id")
    outcome = executor.execute(run_id, spec, scope, saved["goal"], thread_id=thread_id,
                               pause_on_gate=saved.get("pause_on_gate", False))
    result = {"run_id": run_id, "thread_id": thread_id, "routing": saved["routing"],
              "outputs": outcome.outputs}
    if outcome.paused:
        return {**result, "status": runs.WAITING, "synthesis": None,
                "pending_approvals": runs.pending_approvals(run_id)}
    synthesis = OrchestratorAgent().synthesize({"goal": saved["goal"],
                                                "outputs": outcome.outputs})["synthesis"]
    final = {**result, "status": runs.SUCCEEDED, "synthesis": synthesis,
             "budget_fallback": runs.get_state(run_id).get("budget")}
    runs.save_result(run_id, final)
    return final
