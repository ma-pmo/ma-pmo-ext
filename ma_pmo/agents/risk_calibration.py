"""A4's confidence from its evidence, calibrated on what actually happened (roadmap 11).

A4 used to report 0.85 for every alert, so confidence could not tell a good alert from a bad
one (book ch. 12: "uninformative"). Now each task an alert rests on is one of three kinds of
evidence A4 already computes (`risk_signals.py`):

| evidence | the task |
|---|---|
| `blocked` | waits for an unfinished task |
| `stalled` | its predecessors are done but it is below 50% (in a replay: not started) |
| `moving` | anything else still open (started, nothing blocking it) |

`fixtures/a4_calibration.json` gives, per kind, the share of such issues that actually slipped
in the public Jira benchmark's training releases (`ma-pmo benchmark calibrate`), with a 95%
interval. An alert's confidence is the mean of those shares over the tasks it names (blocked
and stalled), or over the project's open tasks when it names none: the chance that what the
alert points at really goes wrong. The kinds are categories, not a scale: in the data blocked
tasks slip less often than stalled ones, so no ordering is assumed.

`MA_PMO_A4_CALIBRATION` points at another file, e.g. one fitted on an organization's history.
"""
from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

from ma_pmo.agents.risk_signals import ProjectSignals

BUNDLED = Path(__file__).resolve().parent.parent / "fixtures" / "a4_calibration.json"
KINDS = ("blocked", "stalled", "moving")


@lru_cache
def load(path: str | None = None) -> dict[str, Any]:
    file = Path(path or os.environ.get("MA_PMO_A4_CALIBRATION") or BUNDLED)
    return json.loads(file.read_text(encoding="utf-8"))


def kind_of(task_id: str, sig: ProjectSignals) -> str:
    if task_id in sig.blocked_tasks:
        return "blocked"
    if task_id in sig.stalled_tasks:
        return "stalled"
    return "moving"


def task_probability(kind: str, table: dict[str, Any] | None = None) -> float:
    return float((table or load())["kinds"][kind]["rate"])


def alert_confidence(sig: ProjectSignals, project: dict, table: dict[str, Any] | None = None
                     ) -> float:
    """The chance that the tasks the alert points at slip, from the calibration table."""
    named = [*sig.blocked_tasks, *sig.stalled_tasks]
    if not named:
        named = [t["task_id"] for t in project.get("tasks", [])
                 if t.get("percent_complete", 0) < 100]
    if not named:
        return task_probability("moving", table)
    return round(sum(task_probability(kind_of(t, sig), table) for t in named) / len(named), 2)
