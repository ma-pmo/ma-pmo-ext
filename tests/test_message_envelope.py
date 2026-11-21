"""Roadmap 8, step 1: every message belongs to a conversation and says what it answers."""
from __future__ import annotations

from fastapi.testclient import TestClient

from ma_pmo.core import protocol
from ma_pmo.core.scenarios import run_scenario
from ma_pmo.core.schemas.message import AgentMessage, Intent, MessagePayload


def _message(**kw):
    return AgentMessage(sender="A1", receiver="A5", intent=Intent.INFORM, task_ref="T",
                        payload=MessagePayload(schema_="note.v1", data={"x": 1}), **kw)


def test_a_message_outside_a_run_starts_its_own_conversation():
    a, b = protocol.publish(_message()), protocol.publish(_message())
    assert a.conversation_id and a.conversation_id.startswith("conv-")
    assert a.conversation_id != b.conversation_id
    reply = protocol.publish(_message(conversation_id=a.conversation_id,
                                      in_reply_to=a.message_id))
    assert reply.conversation_id == a.conversation_id


def test_a_run_is_one_conversation_and_reviews_answer_their_decision():
    from ma_pmo.api.main import app

    trace = run_scenario("go_nogo_decision")
    client = TestClient(app)
    msgs = client.get("/messages", params={"limit": 200}).json()
    conversation = trace["run_id"]  # the run is the conversation
    run_msgs = [m for m in msgs if m["conversation_id"] == conversation]
    assert len(run_msgs) == len(trace["communications"])
    reviews = [m for m in run_msgs if m["schema"] == "review.v1"]
    assert reviews and all(m["in_reply_to"] for m in reviews)
    decision = reviews[0]["in_reply_to"]
    thread = client.get(f"/messages/{decision}/thread").json()
    assert thread["conversation_id"] == conversation
    ids = {m["message_id"] for m in thread["messages"]}
    assert decision in ids and set(thread["replies"][decision]) <= ids
    filtered = client.get("/messages", params={"conversation": conversation, "limit": 500}).json()
    assert {m["message_id"] for m in filtered} == ids
    assert client.get("/messages/nope/thread").status_code == 404
