"""Builder review: A6 checks its gate decisions, and A5 its report, against what A3 and A4 posted.

The variants are the conflicts of the 0.6.0 spike: the demo portfolio plus one project PROJ-X
changed so that a decision contradicts another agent (or, for the controls, does not). The real
A3, A4, A6 and A5 run on their deterministic path through a stand-in tracker in a throwaway
workspace.
"""
from __future__ import annotations

import copy

import pytest
from pydantic import ValidationError

from ma_pmo.agents import registry
from ma_pmo.agents.governance import GovernanceAgent
from ma_pmo.agents.reporting import ReportingAgent
from ma_pmo.agents.resource import ResourceAgent
from ma_pmo.agents.risk import RiskAgent
from ma_pmo.core import executor, llm, runs
from ma_pmo.core.sandbox import sandbox
from ma_pmo.core.schemas.payloads.review_v1 import ReviewV1
from ma_pmo.core.workflow import WorkflowSpec
from ma_pmo.db.models import Project
from ma_pmo.db.session import get_session
from ma_pmo.integrations.registry import get_tracker

SCOPE = "PORTFOLIO#2026-Q1"
TEXT = {"en": "x", "ko": "x"}
GATE = ("gate.no_open_high_risk", "gate.staffed", "gate.allocation_by_deadline")


class Tracker:
    def __init__(self, status: dict) -> None:
        self.status = status

    def get_portfolio_status(self, portfolio_id: str) -> dict:
        return copy.deepcopy(self.status)


def _with_x(base: dict, tasks=None, **change) -> dict:
    """The demo portfolio plus PROJ-X: PROJ-22 (on track: SPI 0.85, slack 7 days) changed."""
    status = copy.deepcopy(base)
    x = copy.deepcopy(next(p for p in status["projects"] if p["project_id"] == "PROJ-22"))
    x.update({"project_id": "PROJ-X", "percent_complete": 85.0, **change})
    x["tasks"] = [{**t, "task_id": "X-" + t["task_id"],
                   "deps": ["X-" + d for d in t.get("deps", [])]}
                  for t in (tasks(x["tasks"]) if tasks else x["tasks"])]
    status["projects"].append(x)
    return status


def _scaled(factor: float):
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
    "too_big": ({"status": "green", "tasks": _scaled(200)},
                {"gate.staffed", "gate.allocation_by_deadline"}, False),
    "alloc_after_deadline": ({"status": "green", "deadline": "2026-01-30",
                              "planned_finish": "2026-01-23", "tasks": _scaled(20)},
                             {"gate.allocation_by_deadline"}, False),
    "red_and_unstaffed": ({"status": "red", "skill": "ml"},
                          {"gate.no_open_high_risk", "gate.staffed"}, False),
}


def _spec(reads: str = "upstream", a6_needs=("A3", "A4")) -> WorkflowSpec:
    return WorkflowSpec.model_validate({
        "id": "t", "title": TEXT, "goal": TEXT, "description": TEXT, "steps": [
            {"id": "A3", "agent": "A3"},
            {"id": "A4", "agent": "A4", "needs": []},
            {"id": "A6", "agent": "A6", "needs": list(a6_needs), "reads": reads,
             "params": {"gate": "G3-execution"}},
            {"id": "A5", "agent": "A5", "needs": ["A6"], "reads": reads},
        ]})


@pytest.fixture
def run(monkeypatch):
    def down(**kw):
        raise RuntimeError("deterministic path")

    monkeypatch.setattr(llm.litellm, "completion", down)

    def go(status: dict, spec: WorkflowSpec) -> list[dict]:
        tracker = Tracker(status)
        monkeypatch.setattr(registry, "_instances", {
            "A3": ResourceAgent(tracker), "A4": RiskAgent(tracker),
            "A5": ReportingAgent(tracker), "A6": GovernanceAgent(tracker)})
        with sandbox("test"):
            x = next(p for p in status["projects"] if p["project_id"] == "PROJ-X")
            with get_session() as s:  # risks and allocations point at a real project
                s.add(Project(id="PROJ-X", portfolio_id=SCOPE, skill=x["skill"],
                              status=x["status"], deadline=x.get("deadline")))
            with runs.track("scenario", "t", SCOPE, state={"spec": spec.model_dump()}) as rid:
                return executor.execute(rid, spec, SCOPE, "goal").outputs
    return go


def _reviews(outputs: list[dict], agent: str | None = None) -> list[dict]:
    return [o["data"] for o in outputs
            if o["schema"] == "review.v1" and (agent is None or o["agent"] == agent)]


@pytest.mark.parametrize("name", sorted(VARIANTS))
def test_every_spike_conflict_is_challenged_and_controls_verified(name, run):
    change, expected, report_fixed = VARIANTS[name]
    change = dict(change)
    outputs = run(_with_x(get_tracker().get_portfolio_status(SCOPE), change.pop("tasks", None),
                          **change), _spec())
    on_x = {r["constraint"]: r for r in _reviews(outputs, "A6") if r["project_id"] == "PROJ-X"}
    assert set(on_x) == set(GATE)  # every constraint judged, none skipped
    assert {c for c, r in on_x.items() if r["verdict"] == "CHALLENGE"} == expected
    for r in on_x.values():
        assert r["role"] == "builder" and r["evidence"] and r["rationale"]
    gate = next(o["data"] for o in outputs if o["schema"] == "gate_review.v1"
                and o["data"]["project_id"] == "PROJ-X")
    if expected:
        assert gate["decision"] == "pass"  # the conflict this catches: a pass A3/A4 contradict
    report = next(o["data"] for o in outputs if o["schema"] == "report.v1")
    [covers] = _reviews(outputs, "A5")
    assert covers["constraint"] == "report.covers_risks" and covers["verdict"] == "VERIFIED"
    added = [k for k in report["key_risks"] if k.startswith("PROJ-X risk")]
    assert bool(added) == report_fixed


def test_the_demo_portfolio_has_no_conflict(run):
    outputs = run(_with_x(get_tracker().get_portfolio_status(SCOPE), status="green"), _spec())
    challenged = [r for r in _reviews(outputs) if r["verdict"] == "CHALLENGE"
                  and r["project_id"] in ("PROJ-14", "PROJ-22", "PROJ-31")]
    passed = {o["data"]["project_id"] for o in outputs if o["schema"] == "gate_review.v1"
              and o["data"]["decision"] == "pass"}
    assert not [r for r in challenged if r["project_id"] in passed]


def test_evidence_points_at_the_posts_it_rests_on(run):
    outputs = run(_with_x(get_tracker().get_portfolio_status(SCOPE), status="red", skill="ml"),
                  _spec())
    on_x = {r["constraint"]: r for r in _reviews(outputs, "A6") if r["project_id"] == "PROJ-X"}
    risk = on_x["gate.no_open_high_risk"]["evidence"]
    assert [e["kind"] for e in risk] == ["message"]
    assert on_x["gate.staffed"]["evidence"] == [
        {"kind": "message", "ref": on_x["gate.staffed"]["evidence"][0]["ref"],
         "field": "unstaffed"}]
    assert {"kind": "tracker", "ref": "PROJ-X", "field": "deadline"} in \
        on_x["gate.allocation_by_deadline"]["evidence"]
    healthy = run(_with_x(get_tracker().get_portfolio_status(SCOPE), status="green"), _spec())
    quiet = next(r for r in _reviews(healthy, "A6") if r["project_id"] == "PROJ-X"
                 and r["constraint"] == "gate.no_open_high_risk")
    assert quiet["evidence"] == [{"kind": "step", "ref": "A4", "field": "PROJ-X"}]  # none found


def test_isolated_steps_review_nothing(run):
    status = _with_x(get_tracker().get_portfolio_status(SCOPE), status="red")
    outputs = run(status, _spec(reads="isolated"))
    assert _reviews(outputs) == []
    report = next(o["data"] for o in outputs if o["schema"] == "report.v1")
    assert not [k for k in report["key_risks"] if "(A4)" in k]


def test_a_constraint_whose_source_is_not_readable_is_not_checked(run):
    status = _with_x(get_tracker().get_portfolio_status(SCOPE), status="red", skill="ml")
    outputs = run(status, _spec(a6_needs=("A4",)))  # A3 runs, but A6 does not wait for it
    on_x = {r["constraint"] for r in _reviews(outputs, "A6") if r["project_id"] == "PROJ-X"}
    assert on_x == {"gate.no_open_high_risk"}
    outputs = run(status, _spec(a6_needs=("A3",)))  # now A4 is the one out of reach
    on_x = {r["constraint"] for r in _reviews(outputs, "A6") if r["project_id"] == "PROJ-X"}
    assert on_x == {"gate.staffed", "gate.allocation_by_deadline"}
    assert _reviews(outputs, "A5") == []  # A5 reads A6 and A3 here, no risks to cover


def test_a_verdict_must_cite_evidence():
    base = {"target": "m", "constraint": "c", "role": "builder"}
    for verdict in ("VERIFIED", "CHALLENGE"):
        with pytest.raises(ValidationError, match="cite"):
            ReviewV1.model_validate({**base, "verdict": verdict})
    with pytest.raises(ValidationError, match="describe"):
        ReviewV1.model_validate({**base, "verdict": "ALTERNATIVE"})
    ok = ReviewV1.model_validate({**base, "verdict": "CHALLENGE",
                                  "evidence": [{"kind": "step", "ref": "A4"}]})
    assert ok.evidence[0].kind == "step"


def test_a_retried_step_gets_the_stored_message_back():
    """Reviews cite their target by id, so a retry must hand back the id that was stored."""
    from ma_pmo.core import protocol
    from ma_pmo.core.schemas.message import AgentMessage, Intent, MessagePayload

    def message() -> AgentMessage:
        return AgentMessage(sender="A6", receiver="A1", intent=Intent.INFORM, task_ref=SCOPE,
                            payload=MessagePayload(schema_="note.v1", data={"n": 1}))

    with runs.track("scenario", "t", SCOPE):
        with pytest.raises(RuntimeError), runs.step("A6", 1):
            first = protocol.publish(message())
            raise RuntimeError("the step fails after publishing")
        with runs.step("A6", 1):  # the retry publishes a new message object
            again = protocol.publish(message())
    assert again.message_id == first.message_id
