"""Workflow versions: one validator, drafts, publishing by an approver, runs pinned to a version."""
from __future__ import annotations

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import delete

from ma_pmo.api.auth import ApiKeyAuthenticator, AuthMiddleware
from ma_pmo.api.main import app, language
from ma_pmo.api.routers import workflows as workflows_router
from ma_pmo.cli import main as cli
from ma_pmo.core import scenarios, workflow_store, workspace
from ma_pmo.core.scenarios import run_scenario
from ma_pmo.db import workspaces
from ma_pmo.db.models import Membership, WorkflowVersion, Workspace
from ma_pmo.db.session import get_session

client = TestClient(app)
GATED = "knowledge_kickoff"  # A7 -> A2 -> A6 (gate G2-planning, required)
OPERATOR = "operator-key-0123456789"
APPROVER = "approver-key-0123456789"


@pytest.fixture(autouse=True)
def clean():
    yield
    for where in ("default", "acme-wf"):
        with workspace.use(where), get_session() as s:
            s.execute(delete(WorkflowVersion))


def _spec(workflow_id: str = GATED) -> dict:
    return scenarios.loaded(workflow_id).model_dump()


def _without(spec: dict, step_id: str) -> dict:
    steps = [s for s in spec["steps"] if s["id"] != step_id]
    return {**spec, "steps": steps}


def _problems(spec: dict) -> list[str]:
    body = client.post("/workflows/validate", json={"spec": spec}).json()
    assert body["ok"] is (not body["problems"])
    return body["problems"]


def test_the_shipped_workflows_pass_the_validator():
    for spec in scenarios.workflows():
        assert _problems(spec.model_dump()) == [], spec.id


@pytest.mark.parametrize("change, reason", [
    (lambda s: _without(s, "A6"), "required step 'A6' (A6) cannot be removed"),
    (lambda s: {**s, "steps": [*s["steps"][:2], {**s["steps"][2], "params": {"gate": "G1"}}]},
     "required step 'A6' (A6) cannot be changed"),
    (lambda s: {**s, "steps": [*s["steps"][:2], {**s["steps"][2], "required": False}]},
     "required step 'A6' (A6) cannot be changed"),
    (lambda s: {**s, "steps": [*s["steps"], {"id": "x", "agent": "A9"}]}, "unknown agents: A9"),
    (lambda s: {**s, "steps": [*s["steps"], {"id": "g", "agent": "A6", "params": {"gate": "G3"}}]},
     "'g' is a gate and must be required"),
    (lambda s: {**s, "category": "misc"}, "unknown category 'misc'"),
    (lambda s: {**s, "ablated": True}, "ablated"),
    (lambda s: {**s, "steps": [{"id": "a", "agent": "A2", "needs": ["b"]},
                               {"id": "b", "agent": "A4", "needs": ["a"]}]},
     "depend on each other"),
])
def test_the_validator_names_what_is_wrong(change, reason):
    assert any(reason in p for p in _problems(change(_spec()))), _problems(change(_spec()))


def test_removing_a_mandatory_gate_is_rejected_by_the_api_not_just_the_ui():
    body = client.post(f"/workflows/{GATED}/versions", json={"spec": _without(_spec(), "A6")})
    assert body.status_code == 422
    assert "cannot be removed" in body.json()["detail"]["problems"][0]
    korean = client.post(f"/workflows/{GATED}/versions?lang=ko",
                         json={"spec": _without(_spec(), "A6")})
    assert "뺄 수 없습니다" in korean.json()["detail"]["problems"][0]
    assert workflow_store.versions(GATED)[-1]["version"] == 1  # nothing was saved


def test_a_draft_changes_nothing_until_it_is_published():
    edited = _without(_spec(), "A7")  # an optional step may go
    edited["steps"][0]["needs"] = []
    saved = client.post(f"/workflows/{GATED}/versions", json={"spec": edited, "note": "no RAG"})
    assert saved.status_code == 201 and saved.json()["version"] == 2
    assert saved.json()["status"] == "draft" and saved.json()["note"] == "no RAG"
    assert client.get(f"/workflows/{GATED}").json()["version"] == 1
    assert run_scenario(GATED)["phases"][1]["agent"] == "A7"

    published = client.post(f"/workflows/{GATED}/versions/2/publish")
    assert published.status_code == 200 and published.json()["status"] == "published"
    now = client.get(f"/workflows/{GATED}").json()
    assert now["version"] == 2 and [s["agent"] for s in now["steps"]] == ["A2", "A6"]
    listed = {w["id"]: w for w in client.get("/workflows").json()["workflows"]}
    assert listed[GATED]["published_here"] and not listed["weekly_status"]["published_here"]

    trace = run_scenario(GATED)
    assert [p["agent"] for p in trace["phases"][1:3]] == ["A2", "A6"]
    run = client.get(f"/runs/{trace['run_id']}/workflow").json()
    assert run["version"] == 2 and run["run"]["workflow_version"] == 2
    assert run["same_as_current"] is True

    versions = client.get(f"/workflows/{GATED}/versions").json()["versions"]
    assert [(v["version"], v["status"], v["in_use"]) for v in versions] == [
        (1, "builtin", False), (2, "published", True)]
    old = client.get(f"/workflows/{GATED}/versions/1").json()
    assert [s["agent"] for s in old["steps"]] == ["A7", "A2", "A6"]  # old versions stay readable
    again = client.post(f"/workflows/{GATED}/versions/2/publish")
    assert again.status_code == 422 and "already published" in again.json()["detail"]["problems"][0]
    assert client.get(f"/workflows/{GATED}/versions/7").status_code == 404


def test_publishing_checks_again_against_the_version_now_in_use():
    stale = client.post(f"/workflows/{GATED}/versions", json={"spec": _spec()}).json()["version"]
    stricter = _spec()
    stricter["steps"].append({"id": "close", "agent": "A6", "params": {"gate": "G4-closure"},
                              "required": True})
    newer = client.post(f"/workflows/{GATED}/versions", json={"spec": stricter}).json()["version"]
    assert client.post(f"/workflows/{GATED}/versions/{newer}/publish").status_code == 200
    late = client.post(f"/workflows/{GATED}/versions/{stale}/publish")
    assert late.status_code == 422
    assert "'close' (A6) cannot be removed" in late.json()["detail"]["problems"][0]


def test_a_new_workflow_starts_at_version_one_and_appears_once_published():
    spec = {**_spec("weekly_status"), "id": "mine", "category": "custom", "version": 7}
    assert client.post("/workflows/other/versions", json={"spec": spec}).status_code == 422
    assert client.post("/workflows/mine/versions", json={"spec": spec}).json()["version"] == 1
    assert "mine" not in {s["id"] for s in client.get("/scenarios").json()}
    client.post("/workflows/mine/versions/1/publish")
    assert "mine" in {s["id"] for s in client.get("/scenarios").json()}
    assert run_scenario("mine")["status"] == "succeeded"


def test_drafting_needs_an_operator_and_publishing_an_approver():
    keys = f"op:operator:{OPERATOR},ap:approver:{APPROVER}"
    secured = FastAPI()
    secured.add_middleware(AuthMiddleware, authenticator=ApiKeyAuthenticator.parse(keys))
    secured.middleware("http")(language)
    secured.include_router(workflows_router.router)
    api = TestClient(secured)
    as_op, as_ap = {"X-API-Key": OPERATOR}, {"X-API-Key": APPROVER}
    assert api.post(f"/workflows/{GATED}/versions", json={"spec": _spec()},
                    headers=as_ap).status_code == 403
    saved = api.post(f"/workflows/{GATED}/versions", json={"spec": _spec()}, headers=as_op)
    assert saved.status_code == 201 and saved.json()["created_by"] == "op"
    assert api.post(f"/workflows/{GATED}/versions/2/publish", headers=as_op).status_code == 403
    done = api.post(f"/workflows/{GATED}/versions/2/publish", headers=as_ap)
    assert done.status_code == 200 and done.json()["published_by"] == "ap"


def test_each_workspace_keeps_its_own_versions():
    workspaces.create("acme-wf", "Acme")
    try:
        with workspace.use("acme-wf"):
            workflow_store.save_draft(_without(_spec(), "A7"), "someone")
            workflow_store.publish(GATED, 2, "someone")
            assert scenarios.workflow(GATED).version == 2
        assert scenarios.workflow(GATED).version == 1
        there = client.get(f"/workflows/{GATED}", headers={workspace.HEADER: "acme-wf"}).json()
        assert there["version"] == 2
        assert client.get(f"/workflows/{GATED}").json()["version"] == 1
        # each workspace numbers its own versions
        assert workflow_store.save_draft(_spec(), "here")["version"] == 2
    finally:
        with get_session() as s:
            s.execute(delete(Membership).where(Membership.workspace_id == "acme-wf"))
        with workspace.use("acme-wf"), get_session() as s:
            s.execute(delete(WorkflowVersion))
        with get_session() as s:
            s.execute(delete(Workspace).where(Workspace.id == "acme-wf"))


def test_the_cli_uses_the_same_validator(tmp_path, capsys):
    good, bad = tmp_path / "good.json", tmp_path / "bad.json"
    good.write_text(json.dumps(_spec()), encoding="utf-8")
    bad.write_text(json.dumps(_without(_spec(), "A6")), encoding="utf-8")
    assert cli(["workflow", "validate", str(good)]) == 0
    assert cli(["workflow", "validate", str(bad)]) == 1
    assert cli(["workflow", "draft", str(bad)]) == 1
    assert cli(["workflow", "draft", str(good), "--note", "same again"]) == 0
    assert cli(["workflow", "publish", GATED, "2"]) == 0
    assert cli(["workflow", "publish", GATED, "9"]) == 1
    assert cli(["workflow", "versions", GATED]) == 0
    out = capsys.readouterr().out
    assert "cannot be removed" in out and "* v2" in out and "same again" in out
