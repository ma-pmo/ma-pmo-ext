"""Sample history for the README screenshots: runs, LLM spend, budgets and recommendations.

The screenshots of the Costs page and the workflow views need some history, and the demo data
has none (without an API key nothing is spent). This script makes it with a stand-in provider:
it answers risk ratings the way a model would and reports token counts, so every figure on
those pages comes from the real ledger, budgets and replay code, but the spend is sample data.
No request leaves the machine.

usage (on a fresh demo database, before starting the API):
    DB_URL=sqlite:///capture.db ma-pmo init-db
    DB_URL=sqlite:///capture.db python docs/capture_seed.py
"""
from __future__ import annotations

import json
import re

import litellm

from ma_pmo.core import budgets, llm, replay
from ma_pmo.core.config import get_settings
from ma_pmo.core.scenarios import run_scenario
from ma_pmo.db import workspaces

FAST = get_settings().llm_model_fast
LABELS = {"PROJ-14": "medium", "PROJ-22": "low", "PROJ-31": "high"}
fast_mode = {"answer": "good"}  # "good" or "wrong": how the fast model rates risks


def completion(**kw):
    """Rate risks like a model would; anything else gets an answer the schema rejects."""
    found = re.search(r"Project: (\S+)", kw["messages"][-1]["content"])
    if found is None:
        content = "{}"  # the agent falls back to its deterministic output, as it does offline
    else:
        project = found.group(1)
        severity = LABELS.get(project, "low")
        if kw["model"] == FAST and fast_mode["answer"] == "wrong":
            severity = "low" if severity != "low" else "high"
        content = json.dumps({"project_id": project, "signal": "schedule slack",
                              "severity": severity, "mitigation": "re-plan the critical path",
                              "rationale": "float is shrinking"})
    response = litellm.ModelResponse(model=kw["model"], usage=litellm.Usage(
        prompt_tokens=6000, completion_tokens=900, total_tokens=6900))
    response.choices[0].message.content = content
    return response


def main() -> None:
    llm.litellm.completion = completion
    if not workspaces.exists("research"):
        workspaces.create("research", "Research lab")
    for scenario in ("weekly_status", "risk_escalation", "executive_briefing",
                     "risk_escalation", "weekly_status"):
        run_scenario(scenario)
    budgets.set_budget("month", 8.0, 10.0, "admin")
    budgets.set_budget("run", None, 0.5, "admin")

    fast_mode["answer"] = "wrong"
    replay.replay("risk_escalation", "A4", repeat=3, by="operator")
    fast_mode["answer"] = "good"
    approved = replay.replay("risk_escalation", "A4", repeat=3, by="operator")
    replay.decide(approved["id"], "approved", "approver")
    replay.replay("executive_briefing", "A4", repeat=3, by="operator")
    print("seeded: runs, spend, budgets and", len(replay.recommendations()), "recommendations")


if __name__ == "__main__":
    main()
