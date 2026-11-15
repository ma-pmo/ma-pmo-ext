"""The 0.6.0 spike as test data: the demo portfolio plus one project PROJ-X in conflict, or not.

PROJ-X starts as PROJ-22 (green, SPI 0.85, slack 7 days, staffed) and each variant changes it so
that a gate decision or the report contradicts another agent. `VARIANTS` gives, per variant, the
change, the gate constraints a reviewer should challenge on PROJ-X, and whether A5's self-check
has to add PROJ-X to the key risks. `run_on` runs real agents on such a portfolio through the
executor, deterministically, in a throwaway workspace.
"""
from __future__ import annotations

from ma_pmo.core.workflow import WorkflowSpec
from ma_pmo.eval.review import SCOPE, run_with
from ma_pmo.eval.review import with_project_x as with_x
from ma_pmo.integrations.registry import get_tracker

TEXT = {"en": "x", "ko": "x"}
GATE = ("gate.no_open_high_risk", "gate.staffed", "gate.allocation_by_deadline")


def scaled(factor: float):
    return lambda ts: [{**t, "effort": t["effort"] * factor} for t in ts]


LATE = {"planned_finish": "2026-03-30", "deadline": "2026-03-20"}
# name -> (PROJ-X, constraints challenged on PROJ-X, report self-check had to add PROJ-X)
VARIANTS = {
    "control_healthy": ({"status": "green"}, set(), False),
    "control_done": ({"status": "green", "percent_complete": 100.0,
                      "tasks": lambda ts: [{**t, "percent_complete": 100.0} for t in ts]},
                     set(), False),
    "red_but_on_spi": ({"status": "red"}, {"gate.no_open_high_risk"}, False),
    "late_finish_green": ({"status": "green", **LATE}, {"gate.no_open_high_risk"}, True),
    "late_finish_amber": ({"status": "amber", **LATE}, {"gate.no_open_high_risk"}, False),
    "stalled_green": ({"status": "green", "tasks": lambda ts: [
        {**ts[0], "percent_complete": 100.0}, {**ts[1], "percent_complete": 40.0}]},
        set(), True),
    "no_skill": ({"status": "green", "skill": "ml"}, {"gate.staffed"}, False),
    "too_big": ({"status": "green", "tasks": scaled(200)},
                {"gate.staffed", "gate.allocation_by_deadline"}, False),
    "alloc_after_deadline": ({"status": "green", "deadline": "2026-01-30",
                              "planned_finish": "2026-01-23", "tasks": scaled(20)},
                             {"gate.allocation_by_deadline"}, False),
    "red_and_unstaffed": ({"status": "red", "skill": "ml"},
                          {"gate.no_open_high_risk", "gate.staffed"}, False),
}



def portfolio(name: str) -> dict:
    """The demo portfolio with PROJ-X as in variant `name`."""
    change = dict(VARIANTS[name][0])
    return with_x(get_tracker().get_portfolio_status(SCOPE), change.pop("tasks", None), **change)


def spec(steps: list[dict], review: bool = False) -> WorkflowSpec:
    return WorkflowSpec.model_validate({"id": "t", "title": TEXT, "goal": TEXT,
                                        "description": TEXT, "steps": steps, "review": review})


def run_on(monkeypatch, status: dict, workflow: WorkflowSpec) -> list[dict]:
    """Run `workflow` with A3, A4, A5, A6 and A8 reading `status`; returns the outputs."""
    return run_full(monkeypatch, status, workflow)["outputs"]


def run_full(monkeypatch, status: dict, workflow: WorkflowSpec, gate: bool = False) -> dict:
    """As `run_on`, plus the commit gate of a reviewed run (or any run, with `gate`) and the
    approval queue after it. The runner is the review evaluation's (ma_pmo/eval/review.py);
    `monkeypatch` stays in the signature so tests can still patch around it."""
    return run_with(status, workflow, gate=gate)


def reviews(outputs: list[dict], agent: str | None = None) -> list[dict]:
    return [o["data"] for o in outputs
            if o["schema"] == "review.v1" and (agent is None or o["agent"] == agent)]
