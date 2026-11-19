"""Report kinds: what a PMO sends to whom.

A workflow picks the kind on its A5 step (`"params": {"kind": "exception"}`); `audience` and
`projects` (a list of project ids, for a project report) can be set the same way.

| kind | for | sections (`KindSpec.sections`) |
|---|---|---|
| status | team and PMO, each period (PRINCE2 highlight) | KPIs, projects, tolerances, risks |
| executive | sponsors, one page | KPIs, exceptions, decisions needed |
| exception | the board, when a tolerance is breached | exceptions, risks |
| gate | a gate or go/no-go meeting | gate decisions, risks, tolerances |
| closure | closing a project or phase | projects, gate decisions, lessons |

Every kind starts with the summary and what changed since the last report, and ends with the
recommended actions.

The narrative without an LLM (`narrate`) follows the kind; with an LLM, `instruction` tells the
model what the kind is for.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import get_args

from ma_pmo.core.i18n import tr
from ma_pmo.core.schemas.payloads.report_v1 import ReportV1
from ma_pmo.core.schemas.payloads.report_v2 import Insight, Kind, ReportFacts


@dataclass(frozen=True)
class KindSpec:
    title: tuple[str, str]  # en, ko
    audience: str
    sections: tuple[str, ...]
    instruction: str


KINDS: dict[str, KindSpec] = {
    "status": KindSpec(
        ("Status report", "상태 보고서"), "team",
        ("summary", "changes", "kpis", "projects", "tolerances", "risks", "actions"),
        "A periodic status (highlight) report for the team and PMO: progress since the last "
        "report, every project's status and forecast, tolerances, risks, next actions."),
    "executive": KindSpec(
        ("Executive summary", "경영진 요약"), "executive",
        ("summary", "changes", "kpis", "exceptions", "decisions", "actions"),
        "A one-page summary for sponsors: lead with what is outside tolerance and what they "
        "must decide; healthy projects get one line at most."),
    "exception": KindSpec(
        ("Exception report", "예외 보고서"), "executive",
        ("summary", "changes", "exceptions", "risks", "actions"),
        "An exception report: which projects breach a tolerance, by how much, why, and the "
        "options to recover (re-plan, add capacity, change scope or deadline)."),
    "gate": KindSpec(
        ("Gate decision pack", "게이트 의사결정 자료"), "executive",
        ("summary", "changes", "decisions", "risks", "tolerances", "actions"),
        "A gate / go-no-go pack: each project's gate decision, the criteria it failed, the "
        "conditions attached, and the risks the decision should weigh."),
    "closure": KindSpec(
        ("Closure report", "종료 보고서"), "team",
        ("summary", "changes", "projects", "decisions", "lessons", "actions"),
        "A closure report: what was delivered against plan, the closure gate, and the lessons "
        "to carry into the next projects."),
}
assert set(KINDS) == set(get_args(Kind))


def spec(kind: str | None) -> KindSpec:
    return KINDS.get(kind or "status", KINDS["status"])


def title(kind: str) -> str:
    en, ko = spec(kind).title
    return tr(en, ko)


def _exceptions(facts: ReportFacts) -> list[str]:
    by_project: dict[str, list[str]] = {}
    for t in facts.breaches:
        if t.dimension == "schedule":
            by_project.setdefault(t.project_id, []).append(
                tr(f"{t.value:g} days past deadline", f"마감 {t.value:g}일 초과"))
        else:
            by_project.setdefault(t.project_id, []).append(
                tr(f"SPI {t.value:g} < {t.limit:g}", f"SPI {t.value:g} < {t.limit:g}"))
    return [f"{pid} ({', '.join(what)})" for pid, what in by_project.items()]


def narrate(kind: str, base: ReportV1, facts: ReportFacts,
            insights: list[Insight] | None = None) -> ReportV1:
    """The rule-based narrative for `kind`, built on the plain rule report `base`, with the
    most important changes since the last report (`insights`) first."""
    exceptions = _exceptions(facts)
    failed = [g for g in facts.gates if g.decision != "pass"]
    lines: list[str] = []
    actions = list(base.recommended_actions)

    if exceptions:
        lines.append(tr(f"Outside tolerance: {'; '.join(exceptions)}.",
                        f"허용 범위 초과: {'; '.join(exceptions)}."))
    elif kind in ("status", "executive", "exception"):
        lines.append(tr("All projects within tolerance.", "모든 프로젝트가 허용 범위 안입니다."))
    if kind in ("gate", "closure", "executive") and facts.gates:
        counts = {d: sum(g.decision == d for g in facts.gates)
                  for d in ("pass", "conditional", "fail")}
        lines.append(tr(
            f"Gate decisions: {counts['pass']} pass, {counts['conditional']} conditional, "
            f"{counts['fail']} fail.",
            f"게이트 결정: 통과 {counts['pass']}, 조건부 {counts['conditional']}, "
            f"불통과 {counts['fail']}."))
    top = [i for i in insights or [] if i.severity != "low"][:3]
    if top:
        lines.insert(0, tr("Since the last report: ", "직전 보고 이후: ")
                     + " ".join(i.text for i in top))
    if kind in ("executive", "gate") and facts.approvals:
        lines.append(tr(f"Waiting for approval: {len(facts.approvals)}.",
                        f"승인 대기: {len(facts.approvals)}건."))
    if kind == "closure":
        lines.append(tr(f"Lessons cited: {len({x.source_id for x in facts.lessons})}.",
                        f"인용된 교훈: {len({x.source_id for x in facts.lessons})}건."))

    if kind in ("exception", "executive"):
        actions = [tr(f"Decide recovery for {e.split(' (')[0]}: re-plan, add capacity, or "
                      "change scope or deadline",
                      f"{e.split(' (')[0]} 회복 방안 결정: 재계획, 인력 보강, 범위·마감 조정")
                   for e in exceptions] or actions
    if kind in ("gate", "executive", "closure"):
        actions += [tr(f"{g.project_id} {g.gate}: resolve {', '.join(g.failed) or 'conditions'} "
                       f"before proceeding",
                       f"{g.project_id} {g.gate}: 진행 전 {', '.join(g.failed) or '조건'} 해결")
                    for g in failed]
    named = " ".join(actions)  # one action per project is enough: skip those already named
    actions += [i.action for i in insights or [] if i.severity == "high"
                and i.action not in actions
                and not (i.project_id and i.project_id in named)]
    summary = " ".join([base.executive_summary, *lines,
                        tr("(rule-based automatic report)", "(규칙기반 자동 보고)")])
    # key risks stay the rule report's: A5's self-check adds what A4 raised (the review stack
    # measures that), and the rendered report lists A4's alerts from the facts anyway
    return base.model_copy(update={"executive_summary": summary,
                                   "recommended_actions": actions})
