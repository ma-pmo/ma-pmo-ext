"""Does the LLM's narrative say what the facts say? Checks every number, date and project id.

The summary, key risks and actions an LLM wrote are scanned for:

- dates (YYYY-MM-DD): must be a date in the facts (as-of, period, deadlines, forecasts);
- ids such as PROJ-31: must be a project in the report (or a risk's, gate's or approval's);
- numbers: must equal a figure in the facts at the precision written (52.9 matches 52.94),
  or its absolute value (slack −7 may be written "7 days late"). Small whole numbers (0 to
  `FREE_INT`) and years pass, as they are mostly counts, ordinals and periods such as
  "2 projects" or "in 2026". The report's scope (e.g. PORTFOLIO#2026-Q1) is not checked.

Anything else is ungrounded. One ungrounded item replaces the whole narrative with the rule
narrative, and the run's trace marks the fallback: a report with one made-up figure is not
sent. Wording is not judged, only what can be checked against the facts.
"""
from __future__ import annotations

import re
from collections.abc import Iterable

from ma_pmo.core.schemas.payloads.report_v1 import ReportV1
from ma_pmo.core.schemas.payloads.report_v2 import Grounding, ReportFacts

FREE_INT = 10
_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
_ID = re.compile(r"\b[A-Z][A-Z0-9]*-[A-Z0-9-]*\d[A-Z0-9-]*\b")
_NUMBER = re.compile(r"(?<![\w.])[-−]?\d+(?:[.,]\d+)?")
_LABELS = re.compile(r"\b(?:Q[1-4]|H[1-5]|G[0-9]-[a-z]+|A[1-8]|W\d{1,2}|v\d+)\b")


def _figures(facts: ReportFacts) -> set[float]:
    values: list[float | None] = []
    for k in facts.kpis:
        values += [k.value, k.previous, k.delta]
    for p in facts.projects:
        values += [p.percent_complete, p.previous_percent_complete, p.spi, p.slack_days]
        if p.previous_percent_complete is not None:
            values.append(p.percent_complete - p.previous_percent_complete)
    for t in facts.tolerances:
        values += [t.value, t.limit]
    values += [len(facts.projects), len(facts.breaches), len(facts.risks), len(facts.gates),
               len(facts.approvals), len({x.source_id for x in facts.lessons})]
    for text in _quoted(facts):  # numbers inside A4's signals and A6's conditions are facts too
        values += [float(n) for n in _NUMBER.findall(_ID.sub(" ", text).replace("−", "-"))
                   if "," not in n]
    out = {float(v) for v in values if v is not None}
    return out | {abs(v) for v in out} | {round(v * 100, 1) for v in out if 0 < abs(v) < 5}


def _quoted(facts: ReportFacts) -> list[str]:
    """Text the facts carry from other agents."""
    texts = [t for r in facts.risks for t in (r.signal, r.mitigation)]
    texts += [t for g in facts.gates for t in (*g.failed, *g.conditions)]
    return texts


def _dates(facts: ReportFacts) -> set[str]:
    days = {facts.as_of, facts.period_start}
    for p in facts.projects:
        days |= {p.deadline, p.forecast_finish}
    return {d for d in days if d}


def _ids(facts: ReportFacts) -> set[str]:
    ids = {p.project_id for p in facts.projects}
    ids |= {r.project_id for r in facts.risks} | {g.project_id for g in facts.gates}
    ids |= {x.source_id for x in facts.lessons}
    ids |= {a.project_id for a in facts.approvals if a.project_id}
    for text in _quoted(facts):  # task ids such as T-3102 in A4's signals
        ids |= set(_ID.findall(text))
    return ids


def _matches(text: str, figures: set[float]) -> bool:
    value = float(text.replace("−", "-").replace(",", "."))
    if value.is_integer() and (0 <= abs(value) <= FREE_INT or 1990 <= value <= 2100):
        return True
    digits = len(text.split(".")[1]) if "." in text else 0
    return any(round(f, digits) == value for f in figures)


def check(narrative: ReportV1, facts: ReportFacts, scope: str = "") -> Grounding:
    figures, dates, ids = _figures(facts), _dates(facts), _ids(facts)
    texts: Iterable[str] = [narrative.executive_summary, *narrative.key_risks,
                            *narrative.recommended_actions,
                            *(p.headline for p in narrative.project_status)]
    checked, bad = 0, []
    for text in texts:
        text = text.replace(scope, " ") if scope else text
        for d in _DATE.findall(text):
            checked += 1
            if d not in dates:
                bad.append(d)
        text = _DATE.sub(" ", text)
        for found in _ID.findall(text):
            checked += 1
            if found not in ids:
                bad.append(found)
        text = _LABELS.sub(" ", _ID.sub(" ", text))
        for n in _NUMBER.findall(text):
            checked += 1
            if not _matches(n, figures):
                bad.append(n)
    for line in narrative.project_status:  # the per-project lines must match the facts
        fact = next((p for p in facts.projects if p.project_id == line.project_id), None)
        checked += 1
        if fact is None or fact.status != line.status or abs(
                fact.percent_complete - line.percent_complete) > 0.5:
            bad.append(f"{line.project_id}: {line.status} {line.percent_complete:g}%")
    return Grounding(checked=checked, ungrounded=list(dict.fromkeys(bad)))
