"""Agent collaboration scenario (use case) engine — for demonstrating and validating the paper.

Selecting a scenario runs a supervisor–worker collaboration in four phases:
  plan     — the A1 orchestrator builds the delegation plan
  execute  — delegated workers (A2–A7) run in sequence, each step instrumented
  complete — A1 synthesizes the outputs
  insight  — five-axis KPI deltas + findings mapped to hypotheses (H1–H5)

Each scenario is designed to provide evidence for specific hypotheses in the paper.
User-facing text follows the active language (see `core/i18n.py`).
"""
from __future__ import annotations

import time
from typing import cast

from sqlalchemy import select

from ma_pmo.agents.orchestrator_rules import deterministic_synthesis
from ma_pmo.core.graph import WORKERS
from ma_pmo.core.i18n import tr
from ma_pmo.core.obs import get_logger
from ma_pmo.core.state.blackboard import PortfolioState
from ma_pmo.db.models import AgentMessageRow, KpiEvent
from ma_pmo.db.session import get_session

_log = get_logger("scenario")

# KPI metrics tracked for insight deltas
_TRACKED = [
    "report_cycle_time_sec",
    "utilization_pct",
    "idle_pct",
    "risk_lead_time_days",
    "risk_detected",
    "spi",
    "projected_slippage_days",
    "gate_review",
    "llm_tokens_total",
]


def _kpi_snapshot() -> dict[str, dict]:
    """(count, sum) snapshot per metric."""
    snap: dict[str, dict] = {}
    with get_session() as s:
        for m in _TRACKED:
            rows = s.query(KpiEvent).filter(KpiEvent.metric == m).all()
            snap[m] = {"count": len(rows), "sum": round(sum(r.value for r in rows), 3)}
    return snap


def _delta(before: dict, after: dict) -> dict:
    """Snapshot delta (events newly recorded by this scenario run)."""
    out = {}
    for m in _TRACKED:
        dc = after[m]["count"] - before[m]["count"]
        if dc > 0:
            new_sum = after[m]["sum"] - before[m]["sum"]
            out[m] = {"new_events": dc, "sum": round(new_sum, 3), "avg": round(new_sum / dc, 3)}
    return out


# ─── insight helpers ────────────────────────────────────────────
def _find(outputs: list[dict], schema: str) -> list[dict]:
    return [o["data"] for o in outputs if o.get("schema") == schema and o.get("data")]


# schema -> (axis, default hypothesis, summarizer) — for generic insights
def _sum_schedule(items):
    return tr(
        f"Schedule and critical path computed for {len(items)} projects; projected finish measured",
        f"{len(items)}개 프로젝트 일정·임계경로 산출, 예상완료 계측",
    )


def _sum_risk(items):
    highs = [r for r in items if r.get("severity") in ("high", "critical")]
    return tr(
        f"{len(items)} risks detected ({len(highs)} high) — early warning secured",
        f"리스크 {len(items)}건 탐지(고위험 {len(highs)}건) — 선행경보 확보",
    )


def _sum_alloc(items):
    a = items[0]
    util = a.get("utilization_pct") or 0
    idle = round(100 - util, 1)
    over = len(a.get("overload_alerts", []))
    return tr(
        f"Resources allocated · utilization {util}% (idle {idle}%) · {over} overloads",
        f"자원 배분 완료 · 활용률 {util}% (유휴 {idle}%) · 과부하 {over}건",
    )


def _sum_report(items):
    summary = items[0].get("executive_summary", "")[:60]
    return tr(f"Executive report auto-generated — {summary}", f"경영 보고 자동 생성 — {summary}")


def _sum_gate(items):
    decisions = [g.get("decision") for g in items]
    return tr(f"Gate review: {decisions}", f"게이트 심사: {decisions}")


def _sum_knowledge(items):
    n = len(items[0].get("citations", []))
    return tr(
        f"{n} lessons learned cited -> evidence for decisions and estimates",
        f"과거 교훈 {n}건 인용 → 판단·견적 근거 확보",
    )


_SCHEMA_INSIGHT = {
    "schedule.v1": ("delivery", "H5", _sum_schedule),
    "risk_alert.v1": ("risk", "H3", _sum_risk),
    "allocation.v1": ("resource", "H2", _sum_alloc),
    "report.v1": ("time", "H1", _sum_report),
    "gate_review.v1": ("delivery", "H3", _sum_gate),
    "knowledge.v1": ("cost", "H4", _sum_knowledge),
}


def _insight_generic(outputs: list[dict], delta: dict, hypotheses: list[str]) -> list[dict]:
    """Derive findings from output schemas and KPI deltas, mapped to scenario hypotheses."""
    findings: list[dict] = []
    for schema, (axis, default_h, summarize) in _SCHEMA_INSIGHT.items():
        items = _find(outputs, schema)
        if not items:
            continue
        hyp = default_h if default_h in hypotheses else (hypotheses[0] if hypotheses else default_h)
        findings.append({"axis": axis, "hypothesis": hyp, "finding": summarize(items)})
    # the RCT delta is evidence for H1
    if "report_cycle_time_sec" in delta and "H1" in hypotheses:
        avg = delta["report_cycle_time_sec"]["avg"]
        findings.append(
            {"axis": "time", "hypothesis": "H1",
             "finding": tr(f"Report cycle time (RCT) measured: avg {avg}s",
                           f"보고 주기 시간(RCT) 계측: 평균 {avg}s")}
        )
    return findings


# ─── scenario definitions (organizational project lifecycle, PMO practice) ──
# category: initiation · execution · governance · closure · portfolio
def _s(title, category, goal, hypotheses, steps, description):
    """title/goal/description are (English, Korean) pairs."""
    return {
        "title": title,
        "category": category,
        "goal": goal,
        "hypotheses": hypotheses,
        "steps": steps,
        "description": description,
    }


SCENARIOS: dict[str, dict] = {
    "knowledge_kickoff": _s(
        ("Knowledge-driven kickoff plan", "지식기반 착수 계획"),
        "initiation",
        ("Kickoff plan reflecting lessons on data-migration delay risk", "데이터 마이그레이션 지연 리스크 교훈 반영 착수 계획"),
        ["H4", "H5"],
        [("A7", {}), ("A2", {}), ("A6", {"gate": "G2-planning"})],
        ("Build the schedule on past lessons learned (RAG) and review the kickoff gate.", "과거 교훈(RAG)을 근거로 일정을 세우고 착수 게이트를 심사한다."),
    ),
    "new_project_intake": _s(
        ("New project intake & feasibility", "신규 프로젝트 인테이크·타당성"),
        "initiation",
        ("Review similar cases, schedule and resource feasibility for a new project", "신규 프로젝트 유사사례·일정·자원 타당성 검토"),
        ["H4", "H5"],
        [("A7", {}), ("A2", {}), ("A3", {}), ("A6", {"gate": "G1-initiation"})],
        ("Search similar cases -> estimate schedule and resources -> initiation gate to validate project selection.", "유사사례 검색→일정·자원 추정→착수 게이트로 프로젝트 선정 타당성을 검증한다."),
    ),
    "baseline_planning": _s(
        ("Baseline planning (schedule + resources)", "기준선 수립(일정+자원)"),
        "initiation",
        ("Set the project baseline (schedule, resources) and pass the planning gate", "프로젝트 기준선(일정·자원) 수립 및 계획완료 게이트"),
        ["H2", "H5"],
        [("A2", {}), ("A3", {}), ("A6", {"gate": "G2-planning"})],
        ("Lock the performance baseline with a CPM schedule and resource allocation.", "CPM 일정과 자원 배분으로 성과관리 기준선(baseline)을 확정한다."),
    ),
    "estimation_review": _s(
        ("Estimate review (based on past cases)", "견적 검증(과거 사례 기반)"),
        "initiation",
        ("Review the evidence behind the payment backend API estimate", "결제 백엔드 API 견적 근거 검토"),
        ["H4"],
        [("A7", {}), ("A2", {})],
        ("Validate a new estimate against actuals from similar past projects.", "과거 유사 프로젝트 실적으로 신규 견적의 타당성을 검증한다."),
    ),
    "quarterly_review": _s(
        ("Quarterly portfolio review", "분기 포트폴리오 통합 리뷰"),
        "execution",
        ("Q1 integrated portfolio review (schedule, risk, executive report)", "Q1 포트폴리오 통합 리뷰(일정·리스크·경영보고)"),
        ["H1", "H3"],
        [("A2", {}), ("A4", {}), ("A5", {})],
        ("Combine schedule, risk and reporting into an auto-generated quarterly review for executives.", "일정·리스크·보고를 통합해 경영진용 분기 리뷰를 자동 생성한다."),
    ),
    "weekly_status": _s(
        ("Weekly status roll-up & report", "주간 상태 취합·보고"),
        "execution",
        ("Collect weekly progress and publish a status report", "주간 진척 상태 취합 및 상태 보고"),
        ["H1"],
        [("A2", {}), ("A5", {})],
        ("Roll up schedule progress into an auto-generated weekly status report (shorter RCT).", "일정 진척을 취합해 주간 상태 보고를 자동 생성한다(RCT 단축)."),
    ),
    "risk_rebalance": _s(
        ("Risk early warning -> resource rebalancing", "리스크 조기경보 → 자원 재배분"),
        "execution",
        ("Risk-driven resource reallocation and gate check", "리스크 기반 자원 재배분 및 게이트 검증"),
        ["H2", "H3"],
        [("A4", {}), ("A3", {}), ("A6", {"gate": "G3-execution"})],
        ("Detect risks early, reallocate resources, then verify with a quality gate.", "리스크를 조기 탐지하고 자원을 재배분한 뒤 품질 게이트로 검증한다."),
    ),
    "schedule_recovery": _s(
        ("Schedule recovery plan", "일정 지연 회복 계획"),
        "execution",
        ("Recover a delayed project schedule and reinforce resources", "지연 프로젝트 일정 회복 및 자원 보강"),
        ["H3", "H2"],
        [("A4", {}), ("A2", {}), ("A3", {})],
        ("Diagnose delay risks and build a recovery plan by recomputing the schedule and adding resources.", "지연 리스크를 진단하고 일정 재계산·자원 보강으로 회복 계획을 세운다."),
    ),
    "resource_conflict": _s(
        ("Resource conflict resolution (multi-project)", "자원 경합 해소(멀티프로젝트)"),
        "execution",
        ("Resolve resource conflicts across multiple projects", "멀티 프로젝트 자원 경합 해소"),
        ["H2", "H3"],
        [("A3", {}), ("A4", {}), ("A6", {"gate": "G3-execution"})],
        ("Resolve cross-project resource contention by optimizing allocation and check load risks.", "프로젝트 간 자원 경합을 배분 최적화로 해소하고 부하 리스크를 점검한다."),
    ),
    "risk_escalation": _s(
        ("High-severity risk escalation", "고위험 리스크 에스컬레이션"),
        "execution",
        ("Escalate high-severity risks and submit for approval", "고위험 리스크 에스컬레이션 및 승인 상신"),
        ["H3"],
        [("A4", {}), ("A6", {"gate": "G3-execution"}), ("A5", {})],
        ("Detect high-severity risks -> gate review -> executive report escalation (HITL approval).", "고위험 리스크를 탐지→게이트 심사→경영 보고로 에스컬레이션(HITL 승인)한다."),
    ),
    "burndown_alert": _s(
        ("Stalled burndown response (event-driven)", "번다운 정체 대응(이벤트 구동)"),
        "execution",
        ("Respond to stalled-burndown risk and replan the schedule", "번다운 정체 리스크 대응 및 일정 재계획"),
        ["H3", "H1"],
        [("A4", {}), ("A2", {}), ("A5", {})],
        ("Detect a stalled burndown signal, replan the schedule and report status.", "번다운 정체 신호를 탐지해 일정을 재계획하고 상태를 보고한다."),
    ),
    "stage_gate_review": _s(
        ("Stage gate review", "스테이지 게이트 심사"),
        "governance",
        ("Planning gate (G2) review and risk check", "계획완료 게이트(G2) 심사 및 리스크 점검"),
        ["H3"],
        [("A2", {}), ("A4", {}), ("A6", {"gate": "G2-planning"})],
        ("Decide whether a stage gate passes based on schedule and risk outputs.", "일정·리스크 산출물을 근거로 스테이지 게이트 통과 여부를 심사한다."),
    ),
    "change_control": _s(
        ("Change control (scope change impact)", "변경 통제(범위 변경 영향)"),
        "governance",
        ("Analyze and approve schedule/resource impact of a scope change", "범위 변경에 따른 일정·자원 영향 분석 및 승인"),
        ["H2", "H5"],
        [("A2", {}), ("A3", {}), ("A6", {"gate": "G3-execution"})],
        ("Analyze the schedule and resource impact of a change request and approve it through a control gate.", "변경 요청의 일정·자원 영향을 분석하고 통제 게이트로 승인 처리한다."),
    ),
    "compliance_audit": _s(
        ("Methodology compliance audit", "방법론 준수 감사"),
        "governance",
        ("Audit methodology and quality-gate compliance and report", "방법론·품질 게이트 준수 감사 및 보고"),
        ["H3"],
        [("A6", {"gate": "G2-planning"}), ("A5", {})],
        ("Audit compliance with the standard methodology using the gate checklist and report.", "표준 방법론 준수 여부를 게이트 체크리스트로 감사하고 보고한다."),
    ),
    "go_nogo_decision": _s(
        ("Go/No-Go decision", "Go/No-Go 의사결정"),
        "governance",
        ("Go/No-Go decision report based on risks and gates", "리스크·게이트 기반 Go/No-Go 의사결정 보고"),
        ["H3", "H1"],
        [("A4", {}), ("A6", {"gate": "G3-execution"}), ("A5", {})],
        ("Combine risks and gate reviews into a go / no-go recommendation for executives.", "리스크와 게이트 심사를 종합해 진행/중단 의사결정을 경영진에 상신한다."),
    ),
    "lessons_learned_closure": _s(
        ("Project closure & lessons learned", "프로젝트 종료·교훈 정리"),
        "closure",
        ("Closure gate and capture of lessons learned", "프로젝트 종료 게이트 및 교훈 지식화"),
        ["H4"],
        [("A6", {"gate": "G4-closure"}), ("A7", {}), ("A5", {})],
        ("Review the closure gate, then retrieve and consolidate lessons back into the knowledge base.", "종료 게이트를 심사하고 교훈을 검색·정리해 지식베이스로 환류한다."),
    ),
    "estimation_calibration": _s(
        ("Estimate calibration (knowledge feedback)", "견적 캘리브레이션(지식 환류)"),
        "closure",
        ("Calibrate estimates from actuals and report", "실적 기반 견적 캘리브레이션 및 보고"),
        ["H4", "H1"],
        [("A7", {}), ("A2", {}), ("A5", {})],
        ("Calibrate the estimation model with lessons from past actuals and report the result.", "과거 실적 교훈으로 견적 모델을 보정하고 결과를 보고한다."),
    ),
    "portfolio_prioritization": _s(
        ("Portfolio prioritization & resource optimization", "포트폴리오 우선순위·자원 최적화"),
        "portfolio",
        ("Prioritize the portfolio by risk and resources", "리스크·자원 기준 포트폴리오 우선순위화"),
        ["H2", "H5"],
        [("A4", {}), ("A3", {}), ("A2", {}), ("A5", {})],
        ("Combine risk, resources and schedule to prioritize the portfolio and optimize resources.", "리스크·자원·일정을 종합해 포트폴리오 우선순위와 자원을 최적화한다."),
    ),
    "executive_briefing": _s(
        ("Integrated executive briefing", "경영진 통합 브리핑"),
        "portfolio",
        ("Executive briefing across all axes (schedule, resources, risk)", "전 축(일정·자원·리스크) 경영진 브리핑"),
        ["H1", "H2", "H3"],
        [("A2", {}), ("A3", {}), ("A4", {}), ("A5", {})],
        ("Roll up schedule, resources and risk across all axes into an auto-generated executive briefing.", "일정·자원·리스크를 전 축으로 취합해 경영진 브리핑을 자동 생성한다."),
    ),
    "capacity_planning": _s(
        ("Capacity planning (demand vs. supply)", "용량 계획(수요-공급)"),
        "portfolio",
        ("Resource demand/supply capacity plan and planning gate", "자원 수요-공급 용량 계획 및 계획완료 게이트"),
        ["H2", "H5"],
        [("A3", {}), ("A2", {}), ("A6", {"gate": "G2-planning"})],
        ("Balance resource demand and supply into a capacity plan and validate it at the gate.", "자원 수요와 공급을 맞춰 용량 계획을 수립하고 게이트로 검증한다."),
    ),
}

# category id -> (English, Korean) label, in display order
CATEGORIES: dict[str, tuple[str, str]] = {
    "initiation": ("Initiation", "착수"),
    "execution": ("Execution", "실행"),
    "governance": ("Governance", "거버넌스"),
    "closure": ("Knowledge & closure", "지식·종료"),
    "portfolio": ("Portfolio", "포트폴리오"),
}

# agent ID -> PMO function label (display)
_AGENT_FN: dict[str, tuple[str, str]] = {
    "A2": ("Planning", "계획"),
    "A3": ("Resources", "자원"),
    "A4": ("Risk", "리스크"),
    "A5": ("Reporting", "보고"),
    "A6": ("Governance", "거버넌스"),
    "A7": ("Knowledge", "지식"),
}


def _fn(agent_id: str) -> str:
    pair = _AGENT_FN.get(agent_id)
    return tr(*pair) if pair else agent_id


def list_scenarios() -> list[dict]:
    return [
        {
            "id": sid,
            "title": tr(*s["title"]),
            "category_id": s["category"],
            "category": tr(*CATEGORIES[s["category"]]),
            "description": tr(*s["description"]),
            "hypotheses": s["hypotheses"],
            "agents": [a for a, _ in s["steps"]],
        }
        for sid, s in SCENARIOS.items()
    ]


def _headline(schema: str, data: dict) -> str:
    from ma_pmo.agents.orchestrator_rules import _headline as h

    return h(schema, data)


def run_scenario(
    scenario_id: str,
    scope: str = "PORTFOLIO#2026-Q1",
    drop_agents: tuple[str, ...] = (),
) -> dict:
    """Run a scenario in four phases (plan -> execute -> complete -> insight); return the trace.

    drop_agents: agents to skip during the execute phase (for ablation experiments).
    """
    if scenario_id not in SCENARIOS:
        raise KeyError(f"unknown scenario: {scenario_id}")
    scen = SCENARIOS[scenario_id]
    steps = [(a, p) for a, p in scen["steps"] if a not in drop_agents]
    title, goal = tr(*scen["title"]), tr(*scen["goal"])
    before = _kpi_snapshot()
    # baseline to pick out only the messages published during this run
    with get_session() as s:
        seen_msg_ids = {m for (m,) in s.execute(select(AgentMessageRow.message_id)).all()}
    phases: list[dict] = []
    _log.info(
        "scenario_start",
        scenario=scenario_id,
        scope=scope,
        agents=[a for a, _ in steps],
        dropped=list(drop_agents),
    )

    # ① plan (A1 delegation plan)
    planned = [{"agent": a, "function": _fn(a), **p} for a, p in steps]
    phases.append(
        {
            "phase": "plan",
            "agent": "A1",
            "title": tr("Plan — orchestrator delegation", "계획 — 오케스트레이터 위임"),
            "detail": tr(
                f"Goal '{goal}' -> delegated to workers {[a for a, _ in steps]}",
                f"목표 '{goal}' → 작업자 {[a for a, _ in steps]} 위임",
            ),
            "delegations": planned,
        }
    )

    # ② execute (workers in sequence)
    all_outputs: list[dict] = []
    for agent_id, params in steps:
        agent = WORKERS[agent_id]
        state = cast(PortfolioState, {"task_ref": scope, "goal": goal, **params})
        _log.info("execute_start", agent=agent_id, function=_fn(agent_id))
        t0 = time.perf_counter()
        result = agent.run(state)
        elapsed_ms = round((time.perf_counter() - t0) * 1000, 1)
        outs = result.get("outputs", [])
        all_outputs.extend(outs)
        _log.info(
            "execute_done",
            agent=agent_id,
            elapsed_ms=elapsed_ms,
            outputs=[o.get("schema") for o in outs],
        )
        phases.append(
            {
                "phase": "execute",
                "agent": agent_id,
                "function": _fn(agent_id),
                "title": tr(
                    f"Execute — {agent_id} {_fn(agent_id)}", f"수행 — {agent_id} {_fn(agent_id)}"
                ),
                "elapsed_ms": elapsed_ms,
                "results": [
                    {
                        "schema": o.get("schema"),
                        "headline": _headline(o.get("schema"), o.get("data") or {}),
                    }
                    for o in outs
                ],
            }
        )

    # ③ complete (A1 synthesis)
    summary = deterministic_synthesis(goal, all_outputs)
    phases.append(
        {
            "phase": "complete",
            "agent": "A1",
            "title": tr("Complete — synthesis", "완료 — 종합"),
            "summary": summary,
        }
    )

    # ④ insight (KPI delta + findings -> hypotheses)
    after = _kpi_snapshot()
    delta = _delta(before, after)
    findings = _insight_generic(all_outputs, delta, scen["hypotheses"])
    phases.append(
        {
            "phase": "insight",
            "title": tr(
                "Insight — five-axis KPIs · hypothesis check", "인사이트 — 5축 KPI · 가설 검증"
            ),
            "kpi_delta": delta,
            "findings": findings,
            "hypotheses": scen["hypotheses"],
        }
    )

    # structured messages exchanged during the run (§4 audit trail) — the "behavior" log
    communications = _new_messages(seen_msg_ids)
    _log.info("scenario_done", scenario=scenario_id, messages=len(communications))

    return {
        "scenario_id": scenario_id,
        "title": title,
        "hypotheses": scen["hypotheses"],
        "scope": scope,
        "phases": phases,
        "communications": communications,
    }


_HYPO_LABEL: dict[str, tuple[str, str]] = {
    "H1": ("shorter reporting time", "보고시간 단축"),
    "H2": ("lower resource idle rate", "자원 유휴율 개선"),
    "H3": ("risk/schedule accuracy", "리스크/일정 정확도"),
    "H4": ("knowledge-driven success rate", "지식 기반 성공률"),
    "H5": ("complexity moderation", "복잡성 조절효과"),
}


def _hypo(h: str) -> str:
    pair = _HYPO_LABEL.get(h)
    return tr(*pair) if pair else ""


def to_paper_markdown(trace: dict) -> str:
    """Render a scenario run as Markdown that can be pasted into the paper."""
    lines: list[str] = []
    hyps = ", ".join(f"{h}({_hypo(h)})" for h in trace["hypotheses"])
    lines.append(tr(f"## Scenario validation: {trace['title']}", f"## 시나리오 검증: {trace['title']}"))
    lines.append("")
    lines.append(tr(f"- **Scope**: `{trace['scope']}`", f"- **대상 범위**: `{trace['scope']}`"))
    lines.append(tr(f"- **Hypotheses**: {hyps}", f"- **검증 가설**: {hyps}"))
    lines.append("")

    # collaboration phases (execute)
    lines.append(tr(
        "### 1) Agent collaboration (plan → execute → complete)",
        "### 1) 에이전트 협업 (계획 → 수행 → 완료)",
    ))
    lines.append("")
    lines.append(tr("| Phase | Agent | Time (ms) | Outputs |", "| 단계 | 에이전트 | 소요(ms) | 산출물 |"))
    lines.append("|---|---|---|---|")
    plan = next(p for p in trace["phases"] if p["phase"] == "plan")
    delegated = ", ".join(d["agent"] for d in plan["delegations"])
    lines.append(tr(
        f"| Plan | A1 | – | delegated: {delegated} |", f"| 계획 | A1 | – | 위임: {delegated} |"
    ))
    for p in trace["phases"]:
        if p["phase"] == "execute":
            outs = ", ".join(r["schema"] for r in p["results"])
            phase = tr("Execute", "수행")
            lines.append(
                f"| {phase} | {p['agent']} {p['function']} | {p['elapsed_ms']} | {outs} |"
            )
    lines.append("")

    # KPI
    insight = next(p for p in trace["phases"] if p["phase"] == "insight")
    if insight.get("kpi_delta"):
        lines.append(tr(
            "### 2) Five-axis KPIs measured (this run's contribution)",
            "### 2) 5축 KPI 실측 (이번 실행 기여분)",
        ))
        lines.append("")
        lines.append(tr("| Metric | New events | Avg |", "| 지표 | 신규 이벤트 | 평균 |"))
        lines.append("|---|---|---|")
        for m, v in insight["kpi_delta"].items():
            lines.append(f"| `{m}` | {v['new_events']} | {v['avg']} |")
        lines.append("")

    # hypothesis check
    lines.append(tr("### 3) Hypothesis results", "### 3) 가설 검증 결과"))
    lines.append("")
    for f in insight["findings"]:
        lines.append(f"- **{f['hypothesis']}** [{f['axis']}] — {f['finding']}")
    lines.append("")

    # audit log
    comms = trace.get("communications", [])
    if comms:
        lines.append(tr(
            "### 4) Structured messages between agents (audit trail, paper §4)",
            "### 4) 에이전트 간 구조화 메시지 (감사 추적, 논문 §4)",
        ))
        lines.append("")
        lines.append(tr(
            "| Sender→Receiver | intent | schema | confidence | HITL |",
            "| 발신→수신 | intent | schema | confidence | HITL |",
        ))
        lines.append("|---|---|---|---|---|")
        for c in comms:
            gate = tr("approval needed", "승인필요") if c["human_gate_required"] else "—"
            lines.append(
                f"| {c['sender']}→{c['receiver']} | {c['intent']} | "
                f"`{c['schema']}` | {c['confidence']} | {gate} |"
            )
        lines.append("")
    lines.append(tr(
        "> Every message is stored in an append-only audit log for reproducibility and "
        "traceability.",
        "> 모든 메시지는 append-only 감사 로그로 저장되어 재현성·추적성을 보장한다.",
    ))
    return "\n".join(lines)


def _new_messages(seen_ids: set[str]) -> list[dict]:
    """agent_message rows (append-only) published since the baseline."""
    with get_session() as s:
        rows = s.scalars(
            select(AgentMessageRow).order_by(AgentMessageRow.timestamp)
        ).all()
        return [
            {
                "message_id": r.message_id,
                "sender": r.sender,
                "receiver": r.receiver,
                "intent": r.intent,
                "schema": r.payload.get("schema") if isinstance(r.payload, dict) else None,
                "task_ref": r.task_ref,
                "confidence": r.confidence,
                "human_gate_required": r.human_gate_required,
                "timestamp": r.timestamp.isoformat() if r.timestamp else None,
            }
            for r in rows
            if r.message_id not in seen_ids
        ]
