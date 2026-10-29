"""Reporters — render experiment results as Markdown, JSON and CSV for papers/docs."""
from __future__ import annotations

import csv
import io
import json
from pathlib import Path

from ma_pmo.core.i18n import tr

_HYPO_LABEL: dict[str, tuple[str, str]] = {
    "H1": ("reporting time", "보고시간"), "H2": ("idle rate", "유휴율"),
    "H3": ("risk/schedule", "리스크/일정"), "H4": ("knowledge/success", "지식/성공률"),
    "H5": ("complexity moderation", "복잡성 조절"),
}


def render_markdown(result: dict) -> str:
    lines: list[str] = []
    lines.append(tr(
        f"# Experiment report: {result['experiment']}", f"# 실험 리포트: {result['experiment']}"
    ))
    lines.append("")
    if result.get("description"):
        lines.append(f"> {result['description']}")
        lines.append("")
    cfg = result["config"]
    scope, n_scn, rep = result["scope"], cfg["scenarios"], cfg["repeat"]
    n_runs = len(result["runs"])
    lines.append(tr(
        f"- Scope: `{scope}` · {n_scn} scenarios · {rep} repetitions · {n_runs} runs total",
        f"- 대상: `{scope}` · 시나리오 {n_scn}개 · 반복 {rep}회 · 총 실행 {n_runs}건",
    ))
    lines.append("")

    # hypothesis coverage
    lines.append(tr("## Hypothesis coverage (H1–H5)", "## 가설 커버리지 (H1~H5)"))
    lines.append("")
    lines.append(
        tr("| Hypothesis | Scenarios | Scenario IDs |", "| 가설 | 검증 시나리오 수 | 시나리오 |")
    )
    lines.append("|---|---|---|")
    for h in ["H1", "H2", "H3", "H4", "H5"]:
        scns = result["coverage"].get(h, [])
        lines.append(f"| {h} {tr(*_HYPO_LABEL[h])} | {len(scns)} | {', '.join(scns) or '—'} |")
    lines.append("")

    # per-scenario aggregate
    lines.append(tr("## Per-scenario summary", "## 시나리오별 실행 요약"))
    lines.append("")
    lines.append(tr(
        "| Scenario | Agents | Hypotheses | Mean time (ms) | ±std | Outputs | Messages | Gated |",
        "| 시나리오 | 에이전트 | 가설 | 평균 소요(ms) | ±std | 산출 | 메시지 | 게이트 |",
    ))
    lines.append("|---|---|---|---|---|---|---|---|")
    for s in result["aggregate"]["per_scenario"]:
        lines.append(
            f"| {s['title']} | {'+'.join(s['agents'])} | {','.join(s['hypotheses'])} | "
            f"{s['elapsed_ms_mean']} | {s['elapsed_ms_std']} | {s['n_outputs']} | "
            f"{s['n_messages']} | {s['n_gated']} |"
        )
    lines.append("")

    # ablation
    if result.get("ablation"):
        lines.append(
            tr("## Ablation (impact of removing an agent)", "## Ablation (에이전트 제외 영향)")
        )
        lines.append("")
        for agent, rows in result["ablation"].items():
            lines.append(tr(f"### Without {agent}", f"### {agent} 제외"))
            lines.append("")
            lines.append(tr(
                "| Scenario | Outputs (base→ablated) | Findings (base→ablated) | Δ findings |",
                "| 시나리오 | 산출(기준→제외) | 발견(기준→제외) | Δ발견 |",
            ))
            lines.append("|---|---|---|---|")
            for r in rows:
                lines.append(
                    f"| {r['scenario_id']} | {r['baseline_outputs']}→{r['ablated_outputs']} | "
                    f"{r['baseline_findings']}→{r['ablated_findings']} | {r['delta_findings']} |"
                )
            lines.append("")
    return "\n".join(lines)


def render_json(result: dict) -> str:
    return json.dumps(result, ensure_ascii=False, indent=2)


def render_csv(result: dict) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["scenario_id", "title", "agents", "hypotheses", "elapsed_ms_mean",
                "elapsed_ms_std", "n_outputs", "n_messages", "n_gated"])
    for s in result["aggregate"]["per_scenario"]:
        w.writerow([
            s["scenario_id"], s["title"], "+".join(s["agents"]),
            ",".join(s["hypotheses"]), s["elapsed_ms_mean"], s["elapsed_ms_std"],
            s["n_outputs"], s["n_messages"], s["n_gated"],
        ])
    return buf.getvalue()


def write_report(result: dict, out_dir: str = "harness/results") -> dict:
    """Write markdown/json/csv files and return their paths."""
    d = Path(out_dir)
    d.mkdir(parents=True, exist_ok=True)
    name = result["experiment"]
    paths = {
        "markdown": d / f"{name}.md",
        "json": d / f"{name}.json",
        "csv": d / f"{name}.csv",
    }
    paths["markdown"].write_text(render_markdown(result), encoding="utf-8")
    paths["json"].write_text(render_json(result), encoding="utf-8")
    paths["csv"].write_text(render_csv(result), encoding="utf-8")
    return {k: str(v) for k, v in paths.items()}
