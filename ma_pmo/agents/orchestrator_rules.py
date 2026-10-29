"""Deterministic fallback for the A1 orchestrator — routing and synthesis without an LLM.

When the LLM gateway fails (no key / outage), the whole pipeline keeps running on rules.
Integration (P5) requirement: orchestration runs end-to-end with no external dependency.
"""
from __future__ import annotations

from ma_pmo.core.i18n import tr
from ma_pmo.core.schemas.payloads.routing_v1 import RoutingDecision, RoutingV1

# keywords (English + Korean) -> (worker, (task in English, task in Korean))
_KEYWORDS: list[tuple[tuple[str, ...], str, tuple[str, str]]] = [
    (
        ("보고", "현황", "리포트", "경영", "report", "status", "executive", "briefing"),
        "A5",
        ("Generate portfolio executive report", "포트폴리오 경영 보고 생성"),
    ),
    (
        ("리스크", "위험", "조기경보", "지연", "risk", "delay", "warning", "escalat"),
        "A4",
        ("Early risk detection", "리스크 조기탐지"),
    ),
    (
        ("일정", "스케줄", "임계경로", "cpm", "plan", "schedule", "critical path", "baseline"),
        "A2",
        ("Compute CPM schedule", "CPM 일정 산출"),
    ),
    (
        ("자원", "배분", "인력", "부하", "유휴", "resource", "allocat", "capacity", "staff"),
        "A3",
        ("Allocate resources", "자원 배분"),
    ),
    (
        ("게이트", "품질", "거버넌스", "방법론", "준수", "gate", "quality", "governance",
         "compliance"),
        "A6",
        ("Gate review", "게이트 심사"),
    ),
    (
        ("지식", "교훈", "유사", "사례", "견적", "knowledge", "lesson", "similar", "estimat"),
        "A7",
        ("Search knowledge and lessons learned", "지식·교훈 검색"),
    ),
]


def keyword_route(goal: str) -> RoutingV1:
    """Pick workers by keywords in the goal; fall back to A5 (reporting) if none match."""
    g = (goal or "").lower()
    dels: list[RoutingDecision] = []
    seen: set[str] = set()
    for keys, agent, task in _KEYWORDS:
        if any(k.lower() in g for k in keys) and agent not in seen:
            dels.append(RoutingDecision(agent=agent, task=tr(*task)))
            seen.add(agent)
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
