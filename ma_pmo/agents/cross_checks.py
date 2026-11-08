"""Cross-checks: does a decision agree with what other steps published? Deterministic, no LLM.

Each check reads the board a step was given (core/board.py), looks at one project, and returns
one verdict with the evidence it rests on, or nothing when the step it needs is not readable
(not checked is not the same as verified). A6 runs the gate checks on its own decisions as a
builder review; A5 runs the report check on its report. A dedicated reviewer can run the same
functions on posts it did not make.

- gate.no_open_high_risk (needs A4): no risk_alert.v1 for the project is high or critical;
- gate.staffed (needs A3): allocation.v1 lists none of the project's work as unstaffed;
- gate.allocation_by_deadline (needs A3): its last planned week is not after its deadline week;
- report.covers_risks (needs A4): every project rated medium or above is among the key risks.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

from ma_pmo.core import protocol
from ma_pmo.core.i18n import tr
from ma_pmo.core.schemas.message import AgentMessage, EvidenceRef, Intent, MessagePayload
from ma_pmo.core.schemas.payloads.review_v1 import ALTERNATIVE, CHALLENGE, VERIFIED, ReviewV1

HIGH = {"high", "critical"}
RISKY = {"medium", "high", "critical"}
GATE_CHECKS = ("gate.no_open_high_risk", "gate.staffed", "gate.allocation_by_deadline")


@dataclass
class Verdict:
    constraint: str
    project_id: str | None
    verdict: str
    evidence: list[EvidenceRef] = field(default_factory=list)
    rationale: str = ""
    alternative: dict | None = None


def _steps_of(steps: list[dict], agent: str) -> list[str]:
    return [s["step"] for s in steps if s["agent"] == agent]


def _posts(board: list[dict], schema: str) -> list[dict]:
    return [p for p in board if p["schema"] == schema]


def _msg(post: dict, field_: str | None = None) -> EvidenceRef:
    return EvidenceRef(kind="message", ref=post["message_id"], field=field_)


def _iso_week(day: str) -> str | None:
    try:
        year, week, _ = date.fromisoformat(day).isocalendar()
    except (TypeError, ValueError):
        return None
    return f"{year}-W{week:02d}"


def no_open_high_risk(project: dict, board: list[dict], steps: list[dict]) -> Verdict | None:
    a4 = _steps_of(steps, "A4")
    if not a4:
        return None
    pid = project["project_id"]
    alerts = [p for p in _posts(board, "risk_alert.v1") if p["data"].get("project_id") == pid]
    high = [p for p in alerts if p["data"].get("severity") in HIGH]
    if high:
        rated = ", ".join(sorted({p["data"]["severity"] for p in high}))
        return Verdict("gate.no_open_high_risk", pid, CHALLENGE, [_msg(p) for p in high],
                       tr(f"A4 rates {pid} {rated}", f"A4가 {pid}를 {rated}로 판정"))
    evidence = [_msg(p) for p in alerts] or [EvidenceRef(kind="step", ref=s, field=pid)
                                             for s in a4]
    return Verdict("gate.no_open_high_risk", pid, VERIFIED, evidence,
                   tr(f"no high or critical risk for {pid}",
                      f"{pid}에 high·critical 리스크 없음"))


def _allocation(board: list[dict], steps: list[dict]) -> dict | None:
    if not _steps_of(steps, "A3"):
        return None
    posts = _posts(board, "allocation.v1")
    return posts[-1] if posts else None


def staffed(project: dict, board: list[dict], steps: list[dict]) -> Verdict | None:
    post = _allocation(board, steps)
    if post is None:
        return None
    pid = project["project_id"]
    short = [u for u in post["data"].get("unstaffed", []) if u.get("project_id") == pid]
    if short:
        hours = sum(u.get("remaining_hours", 0.0) for u in short)
        skills = ", ".join(sorted({u.get("skill", "") for u in short}))
        return Verdict("gate.staffed", pid, CHALLENGE, [_msg(post, "unstaffed")],
                       tr(f"A3 cannot staff {hours:.0f}h of {pid} ({skills})",
                          f"A3가 {pid}의 {hours:.0f}시간을 배정하지 못함({skills})"))
    return Verdict("gate.staffed", pid, VERIFIED, [_msg(post, "unstaffed")],
                   tr(f"A3 staffs all remaining work of {pid}",
                      f"A3가 {pid}의 남은 작업을 모두 배정"))


def allocation_by_deadline(project: dict, board: list[dict],
                           steps: list[dict]) -> Verdict | None:
    post = _allocation(board, steps)
    deadline = _iso_week(project.get("deadline") or "")
    if post is None or deadline is None:
        return None
    pid = project["project_id"]
    weeks = [ln["week"] for ln in post["data"].get("plan", []) if ln.get("project_id") == pid]
    tracker = EvidenceRef(kind="tracker", ref=pid, field="deadline")
    if weeks and max(weeks) > deadline:
        return Verdict("gate.allocation_by_deadline", pid, CHALLENGE, [_msg(post, "plan"), tracker],
                       tr(f"A3 plans {pid} until {max(weeks)}, after its deadline ({deadline})",
                          f"A3 계획상 {pid}는 {max(weeks)}까지로, 마감({deadline}) 이후"))
    return Verdict("gate.allocation_by_deadline", pid, VERIFIED, [_msg(post, "plan"), tracker],
                   tr(f"A3's plan for {pid} ends by its deadline ({deadline})",
                      f"A3 계획상 {pid}는 마감({deadline}) 안에 끝남"))


def gate_checks(project: dict, board: list[dict], steps: list[dict]) -> list[Verdict]:
    """The gate cross-checks that the readable steps allow, for one project."""
    found = (no_open_high_risk(project, board, steps), staffed(project, board, steps),
             allocation_by_deadline(project, board, steps))
    return [v for v in found if v is not None]


def risks_to_report(board: list[dict], steps: list[dict]) -> list[dict] | None:
    """A4's alerts of medium or above, or None when no A4 step is readable."""
    if not _steps_of(steps, "A4"):
        return None
    return [p for p in _posts(board, "risk_alert.v1") if p["data"].get("severity") in RISKY]


def covers_risks(key_risks: list[str], board: list[dict], steps: list[dict]) -> Verdict | None:
    alerts = risks_to_report(board, steps)
    if alerts is None:
        return None
    text = " ".join(key_risks)
    missing = sorted({p["data"]["project_id"] for p in alerts
                      if not re.search(rf"\b{re.escape(p['data']['project_id'])}\b", text)})
    if missing:
        return Verdict("report.covers_risks", None, CHALLENGE,
                       [_msg(p) for p in alerts if p["data"]["project_id"] in missing],
                       tr(f"key risks leave out {', '.join(missing)}",
                          f"핵심 리스크에서 {', '.join(missing)} 누락"))
    evidence = [_msg(p) for p in alerts] or [EvidenceRef(kind="step", ref=s)
                                             for s in _steps_of(steps, "A4")]
    return Verdict("report.covers_risks", None, VERIFIED, evidence,
                   tr("every risk A4 rated medium or above is among the key risks",
                      "A4가 medium 이상으로 본 리스크가 모두 핵심 리스크에 있음"))


# ── alternatives: what else could be decided, for a challenged decision ──────────────────

def _week_start(label: str) -> date:
    year, week = label.split("-W")
    return date.fromisocalendar(int(year), int(week), 1)


def _weeks_until(deadline: str, plan: list[dict]) -> int:
    """Weeks from the start of the plan through the deadline week (at least one)."""
    if not plan:
        return 1
    start = min(_week_start(ln["week"]) for ln in plan)
    return max(1, (_week_start(deadline) - start).days // 7 + 1)


def alternatives(challenge: Verdict, project: dict, board: list[dict],
                 steps: list[dict]) -> list[Verdict]:
    """Decisions a person could take instead of the challenged one, each with what it rests on.

    Deterministic, from the posts behind the challenge:
    - an open high risk: pass only on condition of A4's mitigation;
    - unstaffed work: the hours a week of that skill it would take to finish by the deadline;
    - a plan past the deadline: move the deadline to the plan's last week, or add the hours a
      week that would bring the late work forward.
    """
    pid = project["project_id"]
    found: list[Verdict] = []

    def offer(kind: str, decision: str, summary: str, evidence: list[EvidenceRef],
              **detail: object) -> None:
        found.append(Verdict(f"alternative.{kind}", pid, ALTERNATIVE, evidence, summary,
                             {"kind": kind, "decision": decision, "summary": summary, **detail}))

    if challenge.constraint == "gate.no_open_high_risk":
        for alert in _posts(board, "risk_alert.v1"):
            data = alert["data"]
            if data.get("project_id") == pid and data.get("severity") in HIGH:
                offer("conditional_on_mitigation", "conditional",
                      tr(f"pass {pid} on condition: {data.get('mitigation', '')}",
                         f"조건부 통과({pid}): {data.get('mitigation', '')}"),
                      [_msg(alert, "mitigation")], condition=data.get("mitigation", ""))
    post = _allocation(board, steps)
    deadline = _iso_week(project.get("deadline") or "")
    if post is None or deadline is None:
        return found
    plan = post["data"].get("plan", [])
    weeks = _weeks_until(deadline, plan)
    if challenge.constraint == "gate.staffed":
        for short in post["data"].get("unstaffed", []):
            if short.get("project_id") == pid:
                hours = short.get("remaining_hours", 0.0)
                offer("add_capacity", "conditional",
                      tr(f"add {hours / weeks:.0f} h/week of {short['skill']} to {pid} until "
                         f"{deadline} ({hours:.0f} h unstaffed)",
                         f"{deadline}까지 {pid}에 {short['skill']} 주 {hours / weeks:.0f}시간 추가"
                         f"(미배정 {hours:.0f}시간)"),
                      [_msg(post, "unstaffed"), EvidenceRef(kind="tracker", ref=pid,
                                                            field="deadline")],
                      skill=short["skill"], hours_per_week=round(hours / weeks, 1),
                      until=deadline)
    if challenge.constraint == "gate.allocation_by_deadline":
        mine = [ln for ln in plan if ln.get("project_id") == pid]
        late = [ln for ln in mine if ln["week"] > deadline]
        if late:
            last = max(ln["week"] for ln in mine)
            hours = sum(ln["hours"] for ln in late)
            evidence = [_msg(post, "plan"), EvidenceRef(kind="tracker", ref=pid,
                                                        field="deadline")]
            offer("move_deadline", "conditional",
                  tr(f"move {pid}'s deadline to {last}, when A3's plan ends",
                     f"{pid} 마감을 A3 계획이 끝나는 {last}로 조정"),
                  evidence, new_deadline_week=last)
            offer("add_capacity", "conditional",
                  tr(f"add {hours / weeks:.0f} h/week to {pid} until {deadline} to bring "
                     f"{hours:.0f} late hours forward",
                     f"{deadline}까지 {pid}에 주 {hours / weeks:.0f}시간을 더해 늦은 "
                     f"{hours:.0f}시간을 앞당김"),
                  evidence, hours_per_week=round(hours / weeks, 1), until=deadline)
    return found


def publish_review(agent_id: str, verdict: Verdict, target_id: str, task_ref: str,
                   role: str = "builder") -> dict:
    """Post one verdict on message `target_id` to the log; returns the entry for `outputs`."""
    review = ReviewV1(target=target_id, constraint=verdict.constraint,
                      project_id=verdict.project_id, verdict=verdict.verdict, role=role,
                      evidence=verdict.evidence, rationale=verdict.rationale,
                      alternative=verdict.alternative)
    data = review.model_dump(mode="json", exclude_none=True)
    protocol.publish(AgentMessage(
        sender=agent_id, receiver="A1", intent=Intent.INFORM, task_ref=task_ref,
        payload=MessagePayload(schema_="review.v1", data=data), confidence=0.95,
        evidence=verdict.evidence))
    return {"agent": agent_id, "schema": "review.v1", "data": data}
