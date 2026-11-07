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

from sqlalchemy import select

from ma_pmo.agents import registry
from ma_pmo.agents.orchestrator_rules import deterministic_synthesis
from ma_pmo.core import executor, runs, tracing
from ma_pmo.core.i18n import tr
from ma_pmo.core.obs import get_logger
from ma_pmo.core.workflow import WorkflowSpec, load_workflows
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


# ─── scenario definitions: data in fixtures/workflows.json, see core/workflow.py ──
def _as_scenario(spec: WorkflowSpec) -> dict:
    return {
        "title": spec.title.pair,
        "category": spec.category,
        "goal": spec.goal.pair,
        "hypotheses": spec.hypotheses,
        "steps": [(step.agent, step.params) for step in spec.steps],
        "description": spec.description.pair,
    }


SCENARIOS: dict[str, dict] = {}
_SPECS: dict[str, WorkflowSpec] = {}
workflow_problems: list[str] = []  # files in the workflows folder that could not be used


def reload_workflows(directory: str | None = None) -> list[str]:
    """Read the workflows again; returns what could not be loaded."""
    specs, problems = load_workflows(set(registry.specs()), directory)
    _SPECS.clear()
    _SPECS.update(specs)
    SCENARIOS.clear()
    SCENARIOS.update({sid: _as_scenario(spec) for sid, spec in specs.items()})
    workflow_problems[:] = problems
    for problem in problems:
        _log.warning("workflow_skipped", problem=problem)
    return problems


reload_workflows()

# category id -> (English, Korean) label, in display order
CATEGORIES: dict[str, tuple[str, str]] = {
    "initiation": ("Initiation", "착수"),
    "execution": ("Execution", "실행"),
    "governance": ("Governance", "거버넌스"),
    "closure": ("Knowledge & closure", "지식·종료"),
    "portfolio": ("Portfolio", "포트폴리오"),
    "custom": ("Custom", "사용자 정의"),
}

# agent ID -> PMO function label (display)
_fn = registry.title


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


def run_scenario(
    scenario_id: str,
    scope: str = "PORTFOLIO#2026-Q1",
    drop_agents: tuple[str, ...] = (),
    *,
    pause_on_gate: bool = False,
) -> dict:
    """Run a scenario in four phases (plan -> execute -> complete -> insight); return the trace.

    drop_agents: agents to skip during the execute phase (for ablation experiments).
    pause_on_gate: stop after a step that queued an approval. The trace then has
    status "waiting_approval"; approving continues the run, rejecting cancels it (core/hitl.py).
    One trace per run when tracing is on (see core/tracing.py); every run is recorded
    (see core/runs.py) and its id is returned as `run_id`.
    """
    if scenario_id not in _SPECS:
        raise KeyError(f"unknown scenario: {scenario_id}")
    spec = _SPECS[scenario_id].without_agents(drop_agents)
    state = {"spec": spec.model_dump(), "pause_on_gate": pause_on_gate}
    with tracing.span(f"invoke_workflow {scenario_id}", {
        tracing.OPERATION: "invoke_workflow", tracing.SCENARIO: scenario_id,
        tracing.SCOPE: scope, "ma_pmo.dropped_agents": list(drop_agents),
    }), runs.track("scenario", scenario_id, scope, state=state) as run_id:
        return finish_scenario(run_id, scope)


def finish_scenario(run_id: str, scope: str) -> dict:
    """Run what is left of a scenario, then its complete and insight phases. Also how it resumes.

    The run keeps the workflow it started with, even if the file has changed since.
    """
    saved = runs.get_state(run_id)
    spec = WorkflowSpec.model_validate(saved["spec"])
    title, goal = tr(*spec.title.pair), tr(*spec.goal.pair)
    before = saved.get("kpi_before") or runs.update_state(
        run_id, kpi_before=_kpi_snapshot())["kpi_before"]
    agents = [step.agent for step in spec.steps]
    _log.info("scenario_start", scenario=spec.id, scope=scope, agents=agents)

    # ① plan (A1 delegation plan)
    planned = [{"agent": s.agent, "function": _fn(s.agent), **s.params} for s in spec.steps]
    plan = {
        "phase": "plan",
        "agent": "A1",
        "title": tr("Plan — orchestrator delegation", "계획 — 오케스트레이터 위임"),
        "detail": tr(
            f"Goal '{goal}' -> delegated to workers {agents}",
            f"목표 '{goal}' → 작업자 {agents} 위임",
        ),
        "delegations": planned,
    }

    # ② execute (the workflow's steps)
    outcome = executor.execute(run_id, spec, scope, goal,
                               pause_on_gate=saved.get("pause_on_gate", False))
    phases = [plan, *outcome.phases]

    def trace(status: str) -> dict:
        return {
            "scenario_id": spec.id,
            "title": title,
            "hypotheses": spec.hypotheses,
            "scope": scope,
            "phases": phases,
            # structured messages exchanged during the run (§4 audit trail) — the "behavior" log
            "communications": _run_messages(run_id),
            "run_id": run_id,
            "status": status,
        }

    if outcome.paused:
        return {**trace(runs.WAITING), "pending_approvals": runs.pending_approvals(run_id)}

    # ③ complete (A1 synthesis)
    phases.append(
        {
            "phase": "complete",
            "agent": "A1",
            "title": tr("Complete — synthesis", "완료 — 종합"),
            "summary": deterministic_synthesis(goal, outcome.outputs),
        }
    )

    # ④ insight (KPI delta + findings -> hypotheses)
    delta = _delta(before, _kpi_snapshot())
    phases.append(
        {
            "phase": "insight",
            "title": tr(
                "Insight — five-axis KPIs · hypothesis check", "인사이트 — 5축 KPI · 가설 검증"
            ),
            "kpi_delta": delta,
            "findings": _insight_generic(outcome.outputs, delta, spec.hypotheses),
            "hypotheses": spec.hypotheses,
        }
    )

    final = trace(runs.SUCCEEDED)
    _log.info("scenario_done", scenario=spec.id, messages=len(final["communications"]))
    runs.save_result(run_id, final)
    return final


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


def _run_messages(run_id: str) -> list[dict]:
    """agent_message rows (append-only) published by this run."""
    with get_session() as s:
        rows = s.scalars(
            select(AgentMessageRow).where(AgentMessageRow.run_id == run_id)
            .order_by(AgentMessageRow.timestamp)
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
        ]
