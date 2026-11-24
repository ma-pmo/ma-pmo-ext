"""Budgets: stop spending on LLM calls without stopping the work.

A workspace can set two budgets, each with a warning and a hard limit in USD:

- `month`: everything the workspace spends in the calendar month (UTC);
- `run`: what one run spends.

`check()` runs before every LLM call (core/llm.py). Past a warning, people are told once (a log
line and a `budget.warning` event to the enabled notifiers). Past a hard limit, the call is not
made: `BudgetExceeded` is raised, every agent already treats a failed call by using its
deterministic fallback, so the run carries on and succeeds. The run records why
(`state.budget`), and its result says so.

Spend is what the cost ledger priced (core/costs.py); unpriced calls do not count. The call that
crosses a limit has already been made, so a limit can be passed by at most one call.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select

from ma_pmo.core import runs
from ma_pmo.core.i18n import tr
from ma_pmo.core.obs import get_logger
from ma_pmo.db.models import Budget, LlmCall
from ma_pmo.db.session import get_session

_log = get_logger("budgets")
MONTH, RUN = "month", "run"
KINDS = (MONTH, RUN)


class BudgetExceeded(RuntimeError):
    """A hard limit is reached: use the deterministic fallback instead of calling the LLM."""

    def __init__(self, kind: str, limit: float, spent: float) -> None:
        super().__init__(f"{kind} budget of ${limit:.2f} reached (${spent:.4f} spent)")
        self.kind, self.limit, self.spent = kind, limit, spent


def _month_start(now: datetime | None = None) -> datetime:
    now = now or datetime.now(UTC)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _period(now: datetime | None = None) -> str:
    return _month_start(now).strftime("%Y-%m")


def spent_this_month() -> float:
    with get_session() as s:
        return float(s.scalar(select(func.coalesce(func.sum(LlmCall.usd), 0.0)).where(
            LlmCall.created_at >= _month_start().replace(tzinfo=None))) or 0.0)


def spent_in_run(run_id: str) -> float:
    with get_session() as s:
        return float(s.scalar(select(func.coalesce(func.sum(LlmCall.usd), 0.0)).where(
            LlmCall.run_id == run_id)) or 0.0)


def _budgets() -> dict[str, Budget]:
    with get_session() as s:
        rows = s.scalars(select(Budget)).all()
        for row in rows:
            s.expunge(row)
        return {row.kind: row for row in rows}


def set_budget(kind: str, warn_usd: float | None, limit_usd: float | None, by: str) -> dict:
    """Set (or with both None, remove) a budget. Raises ValueError for a bad one."""
    if kind not in KINDS:
        raise ValueError(tr(f"kind must be {' or '.join(KINDS)}",
                            f"종류는 {' 또는 '.join(KINDS)}여야 합니다"))
    for value in (warn_usd, limit_usd):
        if value is not None and value < 0:
            raise ValueError(tr("amounts cannot be negative", "금액은 음수일 수 없습니다"))
    if warn_usd is not None and limit_usd is not None and warn_usd > limit_usd:
        raise ValueError(tr("the warning must not be above the limit",
                            "경고 금액은 한도보다 클 수 없습니다"))
    with get_session() as s:
        row = s.scalar(select(Budget).where(Budget.kind == kind))
        if warn_usd is None and limit_usd is None:
            if row is not None:
                s.delete(row)
        else:
            if row is None:
                row = Budget(kind=kind)
                s.add(row)
            row.warn_usd, row.limit_usd, row.updated_by = warn_usd, limit_usd, by
            row.updated_at, row.warned_for = datetime.now(UTC), None
    from ma_pmo.core import decisions

    chosen = "removed" if warn_usd is None and limit_usd is None else (
        f"warn {warn_usd} / limit {limit_usd} USD")
    decisions.by_person("budget", kind, f"{kind} budget: {chosen}", by, chosen)
    return status()


def status() -> dict:
    """Each budget with what has been spent against it (the run budget per run)."""
    found = _budgets()

    def limits(b: Budget | None) -> dict:
        return {"warn_usd": b.warn_usd if b else None, "limit_usd": b.limit_usd if b else None,
                "updated_by": b.updated_by if b else None,
                "updated_at": b.updated_at.isoformat() if b else None}

    return {"period": _period(),
            MONTH: {**limits(found.get(MONTH)), "spent_usd": round(spent_this_month(), 6)},
            RUN: limits(found.get(RUN))}


def check(agent: str = "?") -> None:
    """Before an LLM call: warn past a warning, raise BudgetExceeded past a hard limit.

    The limit is the `budget` guardrail (core/guardrails.py, point `spend`), enforced by default:
    in observe mode a call past the limit goes ahead and the guardrail log shows it.
    """
    from ma_pmo.core import guardrails

    result = guardrails.run("budget", {"agent": agent})
    run_id = runs.current_run_id()
    for budget, spent in result.detail.get("_warn", []):
        _warn_once(budget, spent, run_id)
    if result.decision == guardrails.BLOCK:
        budget, spent = result.detail["_limit"]
        _note_fallback(budget, spent, run_id, agent)
        raise BudgetExceeded(budget.kind, budget.limit_usd, spent)  # type: ignore[arg-type]


def _assess(context: dict[str, Any], params: dict[str, Any]) -> Any:
    """The `budget` guardrail: block past a hard limit; note what is past its warning."""
    from ma_pmo.core.guardrails import ALLOW, BLOCK, Result

    found = _budgets()
    run_id = runs.current_run_id()
    spent = [(b, spent_this_month()) for k, b in found.items() if k == MONTH] + [
        (b, spent_in_run(run_id)) for k, b in found.items() if k == RUN and run_id is not None]
    over = [(b, s) for b, s in spent if b.limit_usd is not None and s >= b.limit_usd]
    warn = [(b, s) for b, s in spent if b.warn_usd is not None and s >= b.warn_usd]
    if over:
        budget, used = over[0]
        return Result(BLOCK, f"{budget.kind} budget reached: ${used:.4f} of "
                             f"${budget.limit_usd:.2f}",
                      detail={"_limit": (budget, used), "_warn": warn,
                              "kind": budget.kind, "spent_usd": round(used, 6),
                              "limit_usd": budget.limit_usd})
    return Result(ALLOW, "within budget" if spent else "no budget set",
                  detail={"_warn": warn} if warn else {})


def _note_fallback(budget: Budget, spent: float, run_id: str | None, agent: str) -> None:
    _log.warning("budget_fallback", kind=budget.kind, limit=budget.limit_usd, spent=spent,
                 run_id=run_id, agent=agent)
    if run_id is None:
        return
    state = runs.get_state(run_id)
    if "budget" not in state:  # the first call it stopped is the one worth reporting
        runs.update_state(run_id, budget={
            "kind": budget.kind, "limit_usd": budget.limit_usd, "spent_usd": round(spent, 6),
            "step": runs.current_step_seq(), "agent": agent,
            "at": datetime.now(UTC).isoformat()})


def _warn_once(budget: Budget, spent: float, run_id: str | None) -> None:
    if budget.kind == MONTH:
        period = _period()
        with get_session() as s:
            row = s.scalar(select(Budget).where(Budget.kind == MONTH))
            if row is None or row.warned_for == period:
                return
            row.warned_for = period
    else:
        if run_id is None or runs.get_state(run_id).get("budget_warned"):
            return
        runs.update_state(run_id, budget_warned=True)
    _log.warning("budget_warning", kind=budget.kind, warn=budget.warn_usd, spent=spent,
                 run_id=run_id)
    _notify(budget, spent, run_id)


def _notify(budget: Budget, spent: float, run_id: str | None) -> None:
    from ma_pmo.integrations.base import Event, EventType
    from ma_pmo.integrations.dispatch import emit_later

    what = tr("this month", "이번 달") if budget.kind == MONTH else tr("one run", "실행 1회")
    emit_later([Event(type=EventType.BUDGET_WARNING, severity="warning",
                title=tr(f"LLM spend passed the warning for {what}",
                         f"LLM 비용이 {what} 경고 금액을 넘었습니다"),
                summary=f"${spent:.2f} / ${budget.warn_usd:.2f}"
                        + (f" · limit ${budget.limit_usd:.2f}" if budget.limit_usd else ""),
                task_ref=run_id or "", data={"kind": budget.kind, "spent_usd": spent})])


def fallback_of(run_id: str) -> dict[str, Any] | None:
    """Why a run stopped calling the LLM, if a budget stopped it."""
    budget: dict[str, Any] | None = runs.get_state(run_id).get("budget")
    return budget


def _register() -> None:
    from ma_pmo.core.guardrails import ENFORCE, register

    register("budget", "spend", ENFORCE,
             "Stop LLM calls past a hard budget; agents fall back to their rules")(_assess)


_register()
