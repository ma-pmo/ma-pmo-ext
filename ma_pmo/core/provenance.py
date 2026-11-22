"""W3C PROV export of a decision (roadmap 8, step 4; PROV-O, EU AI Act Art. 12).

`GET /decisions/{id}/provenance` returns the decision as a PROV-JSON document (W3C member
submission, 2013), so a record can be checked with standard tools rather than read from our
tables:

- entities: the decision, the message it was made from, the reviews it was weighed against and
  the evidence those cite (other messages, tracker fields, lessons, steps);
- activities: the run's steps, the commit gate, and the person's approval;
- agents: A1-A8 (`prov:SoftwareAgent`) and people (`prov:Person`);
- relations: `wasGeneratedBy` (a message by its step, the decision by the gate or approval),
  `wasDerivedFrom` (decision from message and reviews, message from its evidence),
  `wasAssociatedWith`, `wasAttributedTo` and `wasInformedBy` (each step by the one before; the
  decision by the steps it rests on).
"""
from __future__ import annotations

import re
from typing import Any
from urllib.parse import quote

from sqlalchemy import select

from ma_pmo.core import decisions
from ma_pmo.core.times import iso
from ma_pmo.db.models import AgentMessageRow, Approval, RunStep
from ma_pmo.db.session import get_session

PREFIXES = {
    "prov": "http://www.w3.org/ns/prov#",
    "mapmo": "urn:ma-pmo:",
    "dec": "urn:ma-pmo:decision:",
    "msg": "urn:ma-pmo:message:",
    "step": "urn:ma-pmo:step:",
    "run": "urn:ma-pmo:run:",
    "approval": "urn:ma-pmo:approval:",
    "agent": "urn:ma-pmo:agent:",
    "person": "urn:ma-pmo:person:",
    "tracker": "urn:ma-pmo:tracker:",
    "knowledge": "urn:ma-pmo:knowledge:",
}
_AGENT = re.compile(r"^A\d+$")


def _q(prefix: str, local: str | int) -> str:
    return f"{prefix}:{quote(str(local), safe='-_.')}"


class _Doc:
    def __init__(self) -> None:
        self.parts: dict[str, dict[str, Any]] = {"prefix": dict(PREFIXES)}
        self._n = 0

    def node(self, kind: str, ident: str, attrs: dict[str, Any] | None = None) -> str:
        bucket = self.parts.setdefault(kind, {})
        bucket.setdefault(ident, {}).update({k: v for k, v in (attrs or {}).items()
                                             if v is not None})
        return ident

    def rel(self, kind: str, **ends: str | None) -> None:
        bucket = self.parts.setdefault(kind, {})
        body = {f"prov:{k}": v for k, v in ends.items() if v is not None}
        if body not in bucket.values():
            self._n += 1
            bucket[f"_:{kind}{self._n}"] = body

    def who(self, name: str) -> str:
        if _AGENT.match(name):
            return self.node("agent", _q("agent", name),
                             {"prov:type": "prov:SoftwareAgent", "prov:label": name})
        return self.node("agent", _q("person", name),
                         {"prov:type": "prov:Person", "prov:label": name})


def _step_of(row: AgentMessageRow) -> str | None:
    """The step that published a message: its dedupe key is run_id:seq:message:n."""
    if not row.dedupe_key or not row.run_id:
        return None
    return _q("step", f"{row.run_id}_{row.dedupe_key.rsplit(':', 3)[1]}")


def _message(doc: _Doc, row: AgentMessageRow, s: Any) -> str:
    payload = row.payload or {}
    ident = doc.node("entity", _q("msg", row.message_id), {
        "prov:type": "mapmo:Message", "prov:label": payload.get("schema"),
        "mapmo:task_ref": row.task_ref, "mapmo:confidence": row.confidence,
        "prov:generatedAtTime": iso(row.timestamp)})
    doc.rel("wasAttributedTo", entity=ident, agent=doc.who(row.sender))
    step = _step_of(row)
    if step:
        doc.rel("wasGeneratedBy", entity=ident, activity=step)
    for ev in row.evidence or []:
        doc.rel("wasDerivedFrom", generatedEntity=ident, usedEntity=_evidence(doc, ev, s))
    return ident


def _evidence(doc: _Doc, ev: dict, s: Any) -> str:
    kind, ref, field = ev.get("kind"), ev.get("ref", ""), ev.get("field")
    if kind == "message":
        row = s.get(AgentMessageRow, ref)
        label = (row.payload or {}).get("schema") if row else None
        ident = doc.node("entity", _q("msg", ref), {"prov:type": "mapmo:Message",
                                                    "prov:label": label})
        if row is not None:
            doc.rel("wasAttributedTo", entity=ident, agent=doc.who(row.sender))
            step = _step_of(row)
            if step:
                doc.rel("wasGeneratedBy", entity=ident, activity=step)
        return ident
    if kind == "tracker":
        return doc.node("entity", _q("tracker", f"{ref}.{field}" if field else ref),
                        {"prov:type": "mapmo:TrackerField", "prov:label": ref,
                         "mapmo:field": field})
    if kind == "knowledge":
        return doc.node("entity", _q("knowledge", ref), {"prov:type": "mapmo:Lesson"})
    return doc.node("entity", _q("mapmo", f"step-output.{ref}.{field or ''}"),
                    {"prov:type": "mapmo:StepOutput", "prov:label": ref, "mapmo:field": field})


def for_decision(record_id: str) -> dict[str, Any] | None:
    """The PROV-JSON document of one decision record; None if there is none here."""
    rec = decisions.get(record_id)
    if rec is None:
        return None
    doc = _Doc()
    outcome = rec["outcome"] or {}
    dec = doc.node("entity", _q("dec", rec["id"]), {
        "prov:type": "mapmo:Decision", "prov:label": rec["title"], "mapmo:kind": rec["kind"],
        "mapmo:subject": rec["subject"], "mapmo:status": rec["status"],
        "mapmo:chosen": outcome.get("chosen"), "mapmo:justification": outcome.get("justification"),
        "prov:generatedAtTime": rec["updated_at"]})
    if rec["supersedes"]:
        doc.rel("wasDerivedFrom", generatedEntity=dec,
                usedEntity=doc.node("entity", _q("dec", rec["supersedes"]),
                                    {"prov:type": "mapmo:Decision"}))
    for maker in rec["decision_makers"]:
        doc.rel("wasAttributedTo", entity=dec, agent=doc.who(maker["who"]))

    with get_session() as s:
        source = s.get(AgentMessageRow, rec["message_id"]) if rec["message_id"] else None
        if source is not None:
            doc.rel("wasDerivedFrom", generatedEntity=dec, usedEntity=_message(doc, source, s))
        for review in rec["consulted"]:
            row = s.get(AgentMessageRow, review.get("message_id") or "")
            if row is not None:
                doc.rel("wasDerivedFrom", generatedEntity=dec, usedEntity=_message(doc, row, s))
        steps = (s.scalars(select(RunStep).where(RunStep.run_id == rec["run_id"])
                           .order_by(RunStep.seq)).all() if rec["run_id"] else [])
        previous = None
        for step in steps:
            act = doc.node("activity", _q("step", f"{step.run_id}_{step.seq}"), {
                "prov:type": "mapmo:RunStep", "prov:label": f"{step.agent} (step {step.seq})",
                "prov:startTime": iso(step.started_at), "prov:endTime": iso(step.finished_at)})
            doc.rel("wasAssociatedWith", activity=act, agent=doc.who(step.agent))
            if previous:
                doc.rel("wasInformedBy", informed=act, informant=previous)
            previous = act
        approval = s.get(Approval, rec["approval_id"]) if rec["approval_id"] else None

        if approval is not None:  # a person decided
            act = doc.node("activity", _q("approval", approval.id), {
                "prov:type": "mapmo:Approval", "prov:label": approval.decision,
                "prov:endTime": iso(approval.decided_at)})
            if approval.approver:
                doc.rel("wasAssociatedWith", activity=act, agent=doc.who(approval.approver))
        elif rec["run_id"]:  # the commit gate let it through, or holds it
            act = doc.node("activity", _q("run", f"{rec['run_id']}.commit"), {
                "prov:type": "mapmo:CommitGate", "prov:label": "commit gate"})
        else:  # decided directly: publishing a workflow, a budget, a recommendation
            act = doc.node("activity", _q("dec", f"{rec['id']}.decide"), {
                "prov:type": "mapmo:Decide", "prov:label": rec["kind"],
                "prov:endTime": rec["created_at"]})
            for maker in rec["decision_makers"]:
                doc.rel("wasAssociatedWith", activity=act, agent=doc.who(maker["who"]))
        doc.rel("wasGeneratedBy", entity=dec, activity=act)
        if source is not None and _step_of(source):
            doc.rel("wasInformedBy", informed=act, informant=_step_of(source))
        elif previous and approval is None and rec["run_id"]:
            doc.rel("wasInformedBy", informed=act, informant=previous)
    return doc.parts
