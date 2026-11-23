"""Questions: an agent asks a person for a fact it needs instead of guessing (roadmap 9, step 3).

Agents ask only for the facts on their reviewed list (`REQUIRED`), and only when that fact is
missing (Horvitz's mixed-initiative principles; Amershi et al., G10: scope services when in
doubt). The asking step calls `require` before it does anything:

- a fact answered earlier in the run is used as given;
- a fact whose question ran out of time is replaced by the question's conservative `default`,
  and the step marks what it produced as unconfirmed;
- otherwise the step stops with `NeedsInput`. The executor leaves that step (and the steps that
  need it) waiting with the run `input_required` (A2A's input-required); other steps go on.

Each question is a `question.v1` message from the agent and a commitment of the person asked
(kind `question`), so it shares the commitments inbox and due-date chain: the person asked is
told, then the accountable person, and when it is due the default is used. An answer resumes the
run.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from ma_pmo.core.i18n import tr

# agent -> the facts it may ask for, and why it cannot work without them
REQUIRED: dict[str, dict[str, str]] = {
    "A2": {"planned_start": "the critical path is dated from the project's start"},
}


@dataclass
class Question:
    key: str  # unique in the run, e.g. PROJ-77.planned_start
    ask: str
    why: str
    answer_type: str  # value | choice | date | yes_no
    default: Any
    project_id: str | None = None
    options: list[str] = field(default_factory=list)


class NeedsInput(Exception):  # noqa: N818 (a request, not an error)
    """The step cannot go on without these answers."""

    def __init__(self, agent: str, questions: list[Question]) -> None:
        super().__init__(f"{agent} needs input: {', '.join(q.key for q in questions)}")
        self.agent, self.questions = agent, questions


def require(state: dict, agent: str, needed: list[Question]) -> dict[str, Any]:
    """The value for each question: answered, else its default if the question timed out.
    Raises NeedsInput with the rest. Asking for a fact not on the agent's list is a bug."""
    allowed = REQUIRED.get(agent, {})
    for q in needed:
        if q.key.rsplit(".", 1)[-1] not in allowed:
            raise ValueError(f"{agent} may not ask for {q.key}: not on its list of facts")
    answers = state.get("answers") or {}
    missing = [q for q in needed if q.key not in answers]
    if missing:
        raise NeedsInput(agent, missing)
    return {q.key: answers[q.key] for q in needed}


def unconfirmed(state: dict, keys: list[str]) -> list[str]:
    """Which of these values are defaults nobody confirmed."""
    return [k for k in keys if k in (state.get("unconfirmed") or [])]


def ask(agent: str, run_id: str | None, step_seq: int | None, q: Question) -> dict:
    """Post the question and track it as a commitment of the person asked."""
    from datetime import timedelta

    from ma_pmo.core import commitments, protocol
    from ma_pmo.core.config import get_settings
    from ma_pmo.core.schemas.message import AgentMessage, Intent, MessagePayload

    due = commitments._today() + timedelta(days=get_settings().question_due_days)
    asked = commitments._owed_by("question", q.project_id)  # its Responsible, else the project
    question_id = commitments.new_id()
    msg = protocol.publish(AgentMessage(
        sender=agent, receiver=asked, intent=Intent.REQUEST,
        task_ref=q.project_id or agent,
        payload=MessagePayload(schema_="question.v1", data={
            "question_id": question_id, "key": q.key, "ask": q.ask, "why": q.why,
            "answer_type": q.answer_type, "options": q.options, "default": q.default,
            "due": due.isoformat(), "project_id": q.project_id})))
    return commitments.create(
        id=question_id, kind="question", debtor=asked, creditor=agent, consequent=q.ask,
        by=agent, due=due,
        project_id=q.project_id, source_message=msg.message_id,
        check={"kind": "question", "key": q.key, "why": q.why, "answer_type": q.answer_type,
               "options": q.options, "default": q.default, "run_id": run_id,
               "step": step_seq})


def check_answer(question: dict, value: Any) -> Any:
    """The answer in the form the question asked for; ValueError if it does not fit."""
    kind, options = question["check"]["answer_type"], question["check"].get("options") or []
    if kind == "date":
        try:
            return date.fromisoformat(str(value)).isoformat()
        except ValueError:
            raise ValueError(tr("give a date as YYYY-MM-DD",
                                "날짜를 YYYY-MM-DD로 입력하세요")) from None
    if kind == "yes_no":
        if isinstance(value, bool):
            return value
        if str(value).lower() in {"yes", "y", "true", "예", "네"}:
            return True
        if str(value).lower() in {"no", "n", "false", "아니오", "아니요"}:
            return False
        raise ValueError(tr("answer yes or no", "예 또는 아니오로 답하세요"))
    if kind == "choice" and str(value) not in options:
        raise ValueError(tr(f"choose one of {options}", f"{options} 중에서 고르세요"))
    if value is None or str(value).strip() == "":
        raise ValueError(tr("the answer is empty", "답이 비어 있습니다"))
    return value


def list_open(run_id: str | None = None) -> list[dict]:
    """Questions still waiting for an answer, soonest due first."""
    from ma_pmo.core import commitments

    found = [c for c in commitments.list_open(limit=1000)
             if c["kind"] == "question" and c["state"] in commitments.OPEN]
    return [c for c in found if run_id is None or (c["check"] or {}).get("run_id") == run_id]


def answer(question_id: str, value: Any, *, by: str) -> dict:
    """Record the answer and resume the run once nothing else is waiting. KeyError for an
    unknown question; ValueError for one already closed or an answer that does not fit."""
    from ma_pmo.core import commitments

    question = commitments.get(question_id)
    if question is None or question["kind"] != "question":
        raise KeyError(question_id)
    if question["state"] not in commitments.OPEN:
        raise ValueError(tr(f"this question is {question['state']}: its default was used"
                            if question["state"] == commitments.VIOLATED
                            else f"this question is {question['state']}",
                            f"이미 {question['state']} 상태인 질문입니다"))
    value = check_answer(question, value)
    commitments.apply(question_id, "discharge", by=by, note=f"answer: {value}",
                      evidence=[{"kind": "answer", "ref": by, "value": value}])
    return {"question_id": question_id, "answer": value,
            "run_status": _deliver(question["check"], value, confirmed=True)}


def use_default(question: dict) -> str | None:
    """A question nobody answered in time: the step goes on with the conservative default."""
    return _deliver(question["check"], question["check"].get("default"), confirmed=False)


def _deliver(check: dict, value: Any, *, confirmed: bool) -> str | None:
    """Put the value in the run and resume it if no other question is open."""
    from ma_pmo.core import runs
    from ma_pmo.core.executor import resume_run

    run_id = check.get("run_id")
    if not run_id:
        return None
    state = runs.get_state(run_id)
    answers = {**(state.get("answers") or {}), check["key"]: value}
    later = [k for k in state.get("unconfirmed") or [] if k != check["key"]]
    runs.update_state(run_id, answers=answers,
                      unconfirmed=later if confirmed else [*later, check["key"]])
    run = runs.get_run(run_id) or {}
    if run.get("status") != runs.INPUT_REQUIRED or list_open(run_id):
        return run.get("status")
    try:
        return resume_run(run_id)["status"]
    except runs.NotResumable:  # e.g. approvals still pending: it resumes when they are decided
        return (runs.get_run(run_id) or {}).get("status")
