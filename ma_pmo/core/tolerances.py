"""Tolerances: how far agents may go on their own (PRINCE2 manage by exception; roadmap 10).

A PMO sets limits per workspace, portfolio and project. Inside them agents decide and the
decision is recorded; when an agent's output forecasts a breach, the `tolerance` guardrail
(point `decision`) raises an exception before it happens: the message goes to the approval
queue, to the Accountable for that decision (roadmap 9), with the forecast and the limit.

| dimension | limit | measured from |
|---|---|---|
| time | `max_slip_days` | schedule.v1: forecast finish against the project deadline |
| quality | `min_spi` | schedule.v1: the project's SPI at the as-of date |
| risk | `max_severity` | risk_alert.v1: the rated severity |
| scope | `max_unstaffed_pct` | allocation.v1: unstaffed hours, as a share of the work left |
| cost | `max_cost_overrun_pct` | not measured yet: the tracker has no cost data |
| benefits | `min_benefit_pct` | not measured yet: the tracker has no benefit data |

Limits live in the policy document (`tolerances`: `workspace`, `portfolios`, `projects`). A
lower level can only narrow the level above: a project's `max_slip_days` cannot exceed its
portfolio's or the workspace's. The guardrail is enforced by default since the evaluation in
docs/GUARDRAILS-EVAL.md; with no limits set it allows everything.
"""
from __future__ import annotations

from datetime import date
from typing import Any

from ma_pmo.core.i18n import tr

SEVERITY = ("low", "medium", "high", "critical")
# limit -> (dimension, "max" or "min", measured)
LIMITS: dict[str, tuple[str, str, bool]] = {
    "max_slip_days": ("time", "max", True),
    "min_spi": ("quality", "min", True),
    "max_severity": ("risk", "max", True),
    "max_unstaffed_pct": ("scope", "max", True),
    "max_cost_overrun_pct": ("cost", "max", False),
    "min_benefit_pct": ("benefits", "min", False),
}
LEVELS = ("workspace", "portfolios", "projects")


def _rank(limit: str, value: Any) -> float:
    """Comparable number for a limit's value (severities by their order)."""
    if limit == "max_severity":
        if value not in SEVERITY:
            raise ValueError(tr(f"max_severity must be one of {SEVERITY}",
                                f"max_severity는 {SEVERITY} 중 하나여야 합니다"))
        return float(SEVERITY.index(value))
    return float(value)


def _tighter(limit: str, a: Any, b: Any) -> Any:
    """The narrower of two values for this limit."""
    kind = LIMITS[limit][1]
    pick = min if kind == "max" else max
    return pick((a, b), key=lambda v: _rank(limit, v))


def document() -> dict[str, Any]:
    from ma_pmo.core import policy

    row = policy._latest()
    return ((row.document if row else {}).get("tolerances") or {})


def effective(project: str | None, portfolio: str | None,
              doc: dict[str, Any] | None = None) -> dict[str, dict[str, Any]]:
    """For each limit set at any level: its value and the level it comes from (the tightest)."""
    doc = document() if doc is None else doc
    layers = [("workspace", doc.get("workspace") or {}),
              (f"portfolio {portfolio}", (doc.get("portfolios") or {}).get(portfolio or "") or {}),
              (f"project {project}", (doc.get("projects") or {}).get(project or "") or {})]
    out: dict[str, dict[str, Any]] = {}
    for level, values in layers:
        for limit, value in values.items():
            if limit not in out or _tighter(limit, out[limit]["value"], value) == value:
                out[limit] = {"value": value, "level": level}
    return out


def validate(doc: dict[str, Any]) -> None:
    """ValueError for an unknown limit or level, or a lower level that widens the one above."""
    for level in doc:
        if level not in LEVELS:
            raise ValueError(tr(f"tolerance level must be one of {LEVELS}",
                                f"허용 범위 단계는 {LEVELS} 중 하나여야 합니다"))
    blocks = [("workspace", None, doc.get("workspace") or {})]
    blocks += [("portfolios", k, v) for k, v in (doc.get("portfolios") or {}).items()]
    blocks += [("projects", k, v) for k, v in (doc.get("projects") or {}).items()]
    for _, _, values in blocks:
        for limit, value in values.items():
            if limit not in LIMITS:
                raise ValueError(tr(f"unknown tolerance: {limit}",
                                    f"없는 허용 범위입니다: {limit}"))
            _rank(limit, value)
    workspace = doc.get("workspace") or {}
    for pid, values in (doc.get("portfolios") or {}).items():
        _narrows(values, workspace, f"portfolio {pid}", "workspace")
    for pid in doc.get("projects") or {}:  # its portfolio's limits apply at run time as well
        narrows_project(doc, pid, None)


def narrows_project(doc: dict[str, Any], project: str, portfolio: str | None) -> None:
    """A project's limits within its portfolio's and the workspace's."""
    values = (doc.get("projects") or {}).get(project) or {}
    _narrows(values, doc.get("workspace") or {}, f"project {project}", "workspace")
    if portfolio:
        _narrows(values, (doc.get("portfolios") or {}).get(portfolio) or {},
                 f"project {project}", f"portfolio {portfolio}")


def _narrows(lower: dict[str, Any], upper: dict[str, Any], name: str, above: str) -> None:
    for limit, value in lower.items():
        if limit in upper and _tighter(limit, value, upper[limit]) != value:
            raise ValueError(tr(
                f"{name}: {limit} {value} is wider than {above}'s {upper[limit]}; a lower level "
                "can only narrow",
                f"{name}: {limit} {value}은(는) {above}의 {upper[limit]}보다 넓습니다. 하위 단계는 "
                "좁히기만 할 수 있습니다"))


# ── the guardrail ─────────────────────────────────────────────────────────────────────

def _project(scope: str, project_id: str) -> dict | None:
    from ma_pmo.agents import common
    from ma_pmo.integrations.registry import get_tracker

    return common.find_project(get_tracker(), scope, project_id)


def _breaches(schema: str, data: dict, scope: str, doc: dict) -> list[dict[str, Any]]:
    from ma_pmo.agents import common

    found: list[dict[str, Any]] = []

    def over(limit: str, project: str | None, forecast: Any) -> None:
        rule = effective(project, scope, doc).get(limit)
        if rule is None or forecast is None or project is None:
            return
        breach = (_rank(limit, forecast) > _rank(limit, rule["value"])
                  if LIMITS[limit][1] == "max"
                  else _rank(limit, forecast) < _rank(limit, rule["value"]))
        if breach:
            found.append({"dimension": LIMITS[limit][0], "limit": limit, "project": project,
                          "tolerance": rule["value"], "level": rule["level"],
                          "forecast": forecast})

    if schema == "schedule.v1":
        pid = data.get("project_id")
        project = _project(scope, pid) if pid else None
        finish = data.get("forecast_finish") or data.get("projected_finish")
        if project and finish and project.get("deadline"):
            slip = (date.fromisoformat(finish) - date.fromisoformat(project["deadline"])).days
            over("max_slip_days", pid, slip)
        if project:
            over("min_spi", pid, common.spi(project))
    elif schema == "risk_alert.v1":
        over("max_severity", data.get("project_id"), data.get("severity"))
    elif schema == "allocation.v1":
        short: dict[str, float] = {}
        for u in data.get("unstaffed") or []:
            short[u["project_id"]] = short.get(u["project_id"], 0.0) + u["remaining_hours"]
        for pid, hours in short.items():
            project = _project(scope, pid)
            left = sum(t.get("effort", 0.0) * (1 - t.get("percent_complete", 0) / 100)
                       for t in (project or {}).get("tasks", []))
            if left > 0:
                over("max_unstaffed_pct", pid, round(100 * hours / left, 1))
    return found


def check(context: dict[str, Any], params: dict[str, Any]) -> Any:
    """The `tolerance` guardrail: ask a person when an output forecasts a breach."""
    from ma_pmo.core.guardrails import ALLOW, ASK, Result

    message = context["message"]
    doc = document()
    if not any(doc.get(level) for level in LEVELS):
        return Result(ALLOW, "no tolerances set")
    scope = message.task_ref.split("/")[0]
    found = _breaches(message.payload.schema_, message.payload.data or {}, scope, doc)
    if not found:
        return Result(ALLOW, "within tolerance")
    return Result(ASK, "; ".join(
        f"{b['project']}: {b['dimension']} {b['forecast']} past {b['limit']} {b['tolerance']} "
        f"({b['level']})" for b in found), detail={"breaches": found})


CHECKED = ("schedule.v1", "risk_alert.v1", "allocation.v1")


def _register() -> None:
    from ma_pmo.core.guardrails import ENFORCE, register

    register("tolerance", "decision", ENFORCE,
             "Raise an exception, as an approval, when an output forecasts a tolerance breach"
             )(check)


_register()
