"""Deterministic fallback for the A1 orchestrator — routing and synthesis without an LLM.

When the LLM gateway fails (no key / outage), the whole pipeline keeps running on rules.
Integration (P5) requirement: orchestration runs end-to-end with no external dependency.
"""
from __future__ import annotations

from ma_pmo.agents import registry
from ma_pmo.core.i18n import tr
from ma_pmo.core.schemas.payloads.routing_v1 import RoutingDecision, RoutingV1


def keyword_route(goal: str) -> RoutingV1:
    """Pick workers by keywords in the goal; fall back to A5 (reporting) if none match."""
    g = (goal or "").lower()
    dels: list[RoutingDecision] = []
    seen: set[str] = set()
    for spec in registry.specs().values():
        if any(k.lower() in g for k in spec.keywords) and spec.id not in seen:
            dels.append(RoutingDecision(agent=spec.id, task=tr(*spec.default_task)))
            seen.add(spec.id)
    if not dels:  # safe fallback: portfolio status report
        dels.append(
            RoutingDecision(agent="A5", task=tr("Portfolio status report", "포트폴리오 현황 보고"))
        )
    agents = [d.agent for d in dels]
    return RoutingV1(
        reasoning=tr(
            f"Rule-based routing (keyword match): {agents}",
            f"규칙기반 라우팅(키워드 매칭): {agents}",
        ),
        delegations=dels,
        finish=False,
    )


def deterministic_synthesis(goal: str, outputs: list[dict]) -> str:
    """Summarize worker outputs into one rule-based paragraph (LLM fallback)."""
    if not outputs:
        return tr("No worker outputs.", "작업자 산출물이 없습니다.")
    parts = [
        tr(
            f"Synthesized {len(outputs)} worker outputs for goal '{goal}'.",
            f"목표 '{goal}' 에 대해 {len(outputs)}개 작업자 산출을 종합했습니다.",
        )
    ]
    for o in outputs:
        agent, schema, data = o.get("agent"), o.get("schema"), o.get("data") or {}
        head = _headline(schema, data)
        parts.append(f"- {agent}({schema}): {head}")
    return " ".join(parts)


def _headline(schema: str | None, data: dict) -> str:
    """One-line key summary per schema."""
    if not data:
        return tr("no output (stub)", "산출 없음(스텁)")
    if schema == "report.v1":
        return data.get("executive_summary", tr("report generated", "보고 생성"))[:120]
    if schema == "risk_alert.v1":
        sig = data.get("signal", "")[:60]
        return tr(
            f"{data.get('project_id')} severity={data.get('severity')} · {sig}",
            f"{data.get('project_id')} 심각도={data.get('severity')} · {sig}",
        )
    if schema == "schedule.v1":
        return tr(
            f"{data.get('project_id')} projected finish={data.get('projected_finish')} "
            f"critical path={data.get('critical_path')}",
            f"{data.get('project_id')} 예상완료={data.get('projected_finish')} "
            f"임계경로={data.get('critical_path')}",
        )
    if schema == "allocation.v1":
        n = len(data.get("plan", []))
        util, over = data.get("utilization_pct"), data.get("overload_alerts")
        return tr(
            f"{n} allocations · utilization={util}% · overloads={over}",
            f"배분 {n}건 · 활용률={util}% · 과부하={over}",
        )
    if schema == "gate_review.v1":
        return f"{data.get('project_id')} {data.get('gate')} → {data.get('decision')}"
    if schema == "knowledge.v1":
        n = len(data.get("citations", []))
        answer = data.get("answer", "")[:80]
        return tr(f"{n} citations · {answer}", f"인용 {n}건 · {answer}")
    return str(data)[:100]
