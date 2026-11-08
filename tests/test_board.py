"""The board: what each step may read of earlier posts, and evidence on messages."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel, ValidationError

from ma_pmo.agents import registry
from ma_pmo.api.main import app
from ma_pmo.core import board, executor, runs, scenarios, workflow_store
from ma_pmo.core.schemas.message import EvidenceRef
from ma_pmo.core.workflow import WorkflowSpec
from ma_pmo.sdk import BaseAgent, board_posts, publish

client = TestClient(app)
TEXT = {"en": "x", "ko": "x"}
SCOPE = "PORTFOLIO#2026-Q1"
ABSENT = "absent"


class Note(BaseModel):
    text: str


class Poster(BaseAgent[Note]):
    """Publishes one post citing what it read, and notes what it was given."""

    def __init__(self, name: str, seen: dict) -> None:
        self.agent_id, self.seen = name, seen

    def run(self, state):
        if "board" in state:
            self.seen[self.agent_id] = [(p["agent"], p["message_id"]) for p in state["board"]]
        else:
            self.seen[self.agent_id] = ABSENT
        cited = [EvidenceRef(kind="message", ref=p["message_id"]) for p in board_posts(state)]
        return {"outputs": [publish(self, "note.v1", Note(text=self.agent_id), task_ref=SCOPE,
                                    evidence=cited)]}


@pytest.fixture
def seen(monkeypatch) -> dict:
    found: dict = {}
    monkeypatch.setattr(registry, "_instances",
                        {a: Poster(a, found) for a in registry.worker_ids()})
    return found


def _spec(steps) -> WorkflowSpec:
    return WorkflowSpec.model_validate(
        {"id": "t", "title": TEXT, "goal": TEXT, "description": TEXT, "steps": steps})


def _run(spec: WorkflowSpec) -> str:
    with runs.track("scenario", "t", SCOPE, state={"spec": spec.model_dump()}) as run_id:
        executor.execute(run_id, spec, SCOPE, "goal")
    return run_id


def _agents(view) -> list[str]:
    return sorted(agent for agent, _id in view)


# A2 -> (A3 | A4) -> A5 -> A6, plus A7 on its own in the first stage
DIAMOND = [
    {"id": "A2", "agent": "A2"},
    {"id": "A7", "agent": "A7", "needs": []},
    {"id": "A3", "agent": "A3", "needs": ["A2"], "reads": "upstream"},
    {"id": "A4", "agent": "A4", "needs": ["A2"]},
    {"id": "A5", "agent": "A5", "needs": ["A3", "A4"], "reads": "upstream"},
    {"id": "A6", "agent": "A6", "needs": ["A5"], "reads": "board"},
]


def test_an_isolated_step_gets_no_board_at_all(seen):
    _run(_spec(DIAMOND))
    assert seen["A2"] == seen["A4"] == seen["A7"] == ABSENT


def test_upstream_reads_only_what_the_step_waits_for(seen):
    _run(_spec(DIAMOND))
    assert _agents(seen["A3"]) == ["A2"]  # not A4, which runs beside it, nor A7
    assert _agents(seen["A5"]) == ["A2", "A3", "A4"]  # A2 through A3 and A4; not A7


def test_board_reads_every_earlier_stage(seen):
    spec = _spec(DIAMOND)
    _run(spec)
    assert _agents(seen["A6"]) == ["A2", "A3", "A4", "A5", "A7"]
    # never a step of its own stage, which may still be running beside it
    as_board = _spec([{**s, "reads": "board"} if s["id"] == "A4" else s for s in DIAMOND])
    assert board.readable(as_board, "A4") == {"A2", "A7"}
    assert board.readable(spec, "A3") == {"A2"} and board.readable(spec, "A2") is None


def test_a_step_sees_the_same_posts_when_asked_again(seen):
    spec = _spec(DIAMOND)
    run_id = _run(spec)
    for step in ("A3", "A5", "A6"):  # what a resumed run would hand the step
        again = [(p["agent"], p["message_id"]) for p in board.view(run_id, spec, step)]
        assert again == seen[step]
    assert board.view(run_id, spec, "A4") is None


def test_another_run_is_never_on_the_board(seen):
    spec = _spec(DIAMOND)
    first = _run(spec)
    second = _run(spec)
    mine = {m for _a, m in seen["A6"]}
    assert mine == {p["message_id"] for p in board.view(second, spec, "A6")}
    assert not mine & {p["message_id"] for p in board.posts(first, spec)}


def test_evidence_is_kept_and_validated(seen):
    spec = _spec(DIAMOND)
    run_id = _run(spec)
    posts = {p["agent"]: p for p in board.posts(run_id, spec)}
    assert posts["A2"]["evidence"] == []
    cited = {e["ref"] for e in posts["A5"]["evidence"]}
    assert cited == {posts[a]["message_id"] for a in ("A2", "A3", "A4")}
    assert all(e == {"kind": "message", "ref": e["ref"]} for e in posts["A5"]["evidence"])
    for bad in ({"kind": "rumour", "ref": "x"}, {"kind": "message", "ref": ""}):
        with pytest.raises(ValidationError):
            EvidenceRef.model_validate(bad)


def test_the_api_shows_posts_and_what_each_step_could_read(seen):
    run_id = _run(_spec(DIAMOND))
    body = client.get(f"/runs/{run_id}/board").json()
    steps = {s["id"]: s for s in body["steps"]}
    assert steps["A4"] == {"id": "A4", "agent": "A4", "reads": "isolated", "can_read": []}
    assert steps["A5"]["can_read"] == ["A2", "A3", "A4"]
    assert [p["step"] for p in body["posts"]] == ["A2", "A7", "A3", "A4", "A5", "A6"]
    assert client.get("/runs/nope/board").status_code == 404


def test_built_in_workflows_stay_isolated():
    for spec in map(scenarios.loaded, scenarios.SCENARIOS):
        assert {s.reads for s in spec.steps} == {"isolated"}, spec.id
    steps = client.get("/workflows/risk_escalation").json()["steps"]
    assert {s["reads"] for s in steps} == {"isolated"}


def test_a_read_mode_is_validated_saved_and_shown():
    spec = scenarios.loaded("risk_escalation").model_dump()
    spec["steps"][1]["reads"] = "upstream"
    assert client.post("/workflows/validate", json={"spec": spec}).json()["ok"] is True
    version = workflow_store.save_draft(spec, "test")["version"]
    try:
        saved = workflow_store.spec_of("risk_escalation", version)
        assert [s.reads for s in saved.steps] == ["isolated", "upstream", "isolated"]
        spec["steps"][1]["reads"] = "everything"
        problems = client.post("/workflows/validate", json={"spec": spec}).json()["problems"]
        assert problems and "reads" in problems[0]
    finally:
        from sqlalchemy import delete

        from ma_pmo.db.models import WorkflowVersion
        from ma_pmo.db.session import get_session

        with get_session() as s:
            s.execute(delete(WorkflowVersion))
