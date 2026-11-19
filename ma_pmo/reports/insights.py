"""What changed since the last report, found by rules over the facts (no LLM).

| insight | when | severity |
|---|---|---|
| `breach.new` | a tolerance is breached that was not in the previous report | high |
| `breach.cleared` | a tolerance breached in the previous report no longer is | low |
| `status.worse` | a project's RAG got worse | high if now red, else medium |
| `status.better` | a project's RAG got better | low |
| `forecast.slipped` | the forecast finish moved `SLIP_DAYS` or more later | medium; high if late |
| `progress.stalled` | no progress since an earlier-dated report, not finished | medium |
| `risk.new` | A4 rates a project high or critical; the previous report read A4 and had not | high |
| `trend.spi_down` | the portfolio SPI fell in each of the last `TREND` reports | medium |

Every insight cites the facts it rests on (`fact_ids`) and suggests an action. They are ranked
by severity, so a reader sees the exceptions first. The first report of a scope and kind has
nothing to compare with and gets no insights.
"""
from __future__ import annotations

from datetime import date
from typing import Any

from ma_pmo.core.i18n import tr
from ma_pmo.core.schemas.payloads.report_v2 import Insight, ReportFacts

SLIP_DAYS = 7
TREND = 3
_ORDER = {"high": 0, "medium": 1, "low": 2}
_RANK = {"green": 0, "amber": 1, "red": 2}


def _days(a: str | None, b: str | None) -> int | None:
    try:
        return (date.fromisoformat(b) - date.fromisoformat(a)).days if a and b else None
    except ValueError:
        return None


def build(facts: ReportFacts, earlier: list[tuple[str, str, dict[str, Any]]]) -> list[Insight]:
    """Insights for `facts`, compared with `earlier` reports (newest first)."""
    if not earlier:
        return []
    prev_id, prev_as_of, prev = earlier[0]
    elapsed = _days(prev_as_of, facts.as_of) or 0
    pf = prev.get("facts") or {}
    prev_projects = {p["project_id"]: p for p in pf.get("projects", [])}
    prev_breaches = {t["id"] for t in pf.get("tolerances", []) if t.get("breached")}
    prev_high = {r["project_id"] for r in pf.get("risks", [])
                 if r.get("severity") in ("high", "critical")}
    out: list[Insight] = []

    def add(id_: str, kind: str, severity: str, text: str, action: str, fact_ids: list[str],
            project: str | None = None) -> None:
        out.append(Insight(id=id_, kind=kind, severity=severity, project_id=project, text=text,
                           action=action, fact_ids=fact_ids))

    for t in facts.tolerances:
        what = (tr(f"forecast {t.value:g} days past the deadline",
                   f"예상 완료가 마감보다 {t.value:g}일 늦음")
                if t.dimension == "schedule" else f"SPI {t.value:g} < {t.limit:g}")
        if t.breached and t.id not in prev_breaches and pf:
            add(f"insight.breach.new.{t.id}", "breach.new", "high",
                tr(f"{t.project_id} left tolerance: {what}.",
                   f"{t.project_id} 허용 범위 이탈: {what}."),
                tr(f"Raise an exception for {t.project_id} and agree a recovery plan.",
                   f"{t.project_id} 예외 보고 후 회복 계획 합의"),
                [t.id, f"project.{t.project_id}"], t.project_id)
        elif not t.breached and t.id in prev_breaches:
            add(f"insight.breach.cleared.{t.id}", "breach.cleared", "low",
                tr(f"{t.project_id} is back within its {t.dimension} tolerance.",
                   f"{t.project_id} {t.dimension} 허용 범위 복귀."),
                tr("Close the exception.", "예외 종료"), [t.id], t.project_id)

    for p in facts.projects:
        before = prev_projects.get(p.project_id)
        if before is None:
            continue
        old = before.get("status")
        if old and old != p.status:
            worse = _RANK[p.status] > _RANK.get(old, 0)
            add(f"insight.status.{p.project_id}", "status.worse" if worse else "status.better",
                ("high" if p.status == "red" else "medium") if worse else "low",
                tr(f"{p.project_id} went from {old} to {p.status}.",
                   f"{p.project_id} 상태 변화: {old} → {p.status}."),
                tr(f"Find out what changed on {p.project_id}.",
                   f"{p.project_id}에서 무엇이 바뀌었는지 확인") if worse
                else tr("Keep the current plan.", "현재 계획 유지"),
                [p.id], p.project_id)
        moved = _days(before.get("forecast_finish"), p.forecast_finish)
        if moved is not None and moved >= SLIP_DAYS:
            late = p.slack_days is not None and p.slack_days < 0
            add(f"insight.forecast.{p.project_id}", "forecast.slipped",
                "high" if late else "medium",
                tr(f"{p.project_id}'s forecast finish moved {moved} days later, to "
                   f"{p.forecast_finish}.",
                   f"{p.project_id} 예상 완료일 {moved}일 지연(현재 {p.forecast_finish})."),
                tr(f"Check the critical path of {p.project_id}.",
                   f"{p.project_id} 임계 경로 점검"), [p.id], p.project_id)
        was = before.get("percent_complete")
        if elapsed > 0 and was is not None and p.percent_complete < 100 \
                and p.percent_complete <= was:
            add(f"insight.stalled.{p.project_id}", "progress.stalled", "medium",
                tr(f"{p.project_id} made no progress since the last report "
                   f"({p.percent_complete:g}%).",
                   f"{p.project_id} 직전 보고 이후 진척 없음({p.percent_complete:g}%)."),
                tr(f"Ask {p.project_id}'s owner what is blocking it.",
                   f"{p.project_id} 담당자에게 막힌 곳 확인"), [p.id], p.project_id)

    seen: set[str] = set()
    for r in facts.risks:
        if (r.severity in ("high", "critical") and r.project_id not in prev_high
                and r.project_id not in seen and pf.get("risks_read")):
            seen.add(r.project_id)
            add(f"insight.risk.{r.project_id}", "risk.new", "high",
                tr(f"New {r.severity} risk on {r.project_id}: {r.signal}.",
                   f"{r.project_id} 새 {r.severity} 리스크: {r.signal}."),
                r.mitigation or tr("Assign an owner to the risk.", "리스크 담당자 지정"),
                [r.id], r.project_id)

    spis = [k.value for k in facts.kpis if k.id == "kpi.spi"]
    for _, _, content in earlier[:TREND - 1]:
        spis += [k.get("value") for k in (content.get("facts") or {}).get("kpis", [])
                 if k.get("id") == "kpi.spi"]
    last = [v for v in spis[:TREND] if v is not None]
    if len(last) == TREND and all(last[i] < last[i + 1] for i in range(TREND - 1)):  # newest 1st
        series = " → ".join(f"{v:g}" for v in reversed(last))
        add("insight.trend.spi", "trend.spi_down", "medium",
            tr(f"Portfolio SPI has fallen {TREND} reports in a row ({series}).",
               f"포트폴리오 SPI가 {TREND}회 연속 하락({series})."),
            tr("Review capacity across the portfolio.", "포트폴리오 전체 인력 검토"),
            ["kpi.spi"])

    out.sort(key=lambda i: _ORDER[i.severity])
    return [i.model_copy(update={"previous_report_id": prev_id}) for i in out]
