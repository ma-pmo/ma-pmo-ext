"""Evaluation report template — turn H1–H5 results into a paper/executive-ready report.

    ma-pmo template report --format md|html [--data ./my-org] [--out report.html]
    GET /eval/report?format=md|html

The report has: a verdict table (one row per hypothesis), per-hypothesis details, the
five-axis KPI summary, the data source and the standard limitations. Text follows the
active language (English/Korean).
"""
from __future__ import annotations

import html
from datetime import UTC, datetime
from typing import Any

from ma_pmo import __version__
from ma_pmo.core.i18n import get_lang, tr
from ma_pmo.eval.aggregate import metric_summary

# verdict keys -> (English, Korean, colour for HTML)
_VERDICT = {
    "supported": ("Supported", "지지됨", "#1a7f37"),
    "not_supported": ("Not supported", "지지 안 됨", "#cf222e"),
    "partial": ("Partly supported", "부분 지지", "#9a6700"),
    "insufficient": ("Insufficient data", "데이터 부족", "#6e7781"),
}

_KPI_ROWS = [
    ("time", "report_cycle_time_sec", ("Report cycle time (s)", "보고 주기 시간(초)")),
    ("resource", "utilization_pct", ("Utilization (%)", "활용률(%)")),
    ("resource", "idle_pct", ("Idle rate (%)", "유휴율(%)")),
    ("delivery", "spi", ("SPI", "SPI")),
    ("delivery", "projected_slippage_days", ("Projected slippage (days)", "예상 지연(일)")),
    ("delivery", "gate_review", ("Gate score (0–1)", "게이트 점수(0~1)")),
    ("risk", "risk_lead_time_days", ("Risk lead time (days)", "리스크 선행시간(일)")),
    ("risk", "risk_detected", ("Risks detected", "탐지 리스크 수")),
    ("cost", "llm_tokens_total", ("LLM tokens", "LLM 토큰")),
]


def _fmt(v: Any, digits: int = 2) -> str:
    if v is None:
        return "–"
    if isinstance(v, float):
        return f"{v:.{digits}f}".rstrip("0").rstrip(".") if v != int(v) else str(int(v))
    return str(v)


def summarize(results: dict) -> list[dict]:
    """One row per hypothesis: claim, key evidence, verdict key."""
    h1, h2, h3, h4, h5 = (results.get(k, {}) for k in ("H1", "H2", "H3", "H4", "H5"))
    rows = []

    red = h1.get("reduction_pct")
    rows.append({
        "id": "H1",
        "claim": tr("Agents shorten the report cycle", "에이전트가 보고 주기를 단축한다"),
        "evidence": tr(
            f"manual {_fmt(h1.get('baseline_manual_sec'))}s → automated "
            f"{_fmt(h1.get('automated_avg_sec'))}s ({_fmt(red, 1)}% shorter, n={h1.get('n', 0)})",
            f"수작업 {_fmt(h1.get('baseline_manual_sec'))}초 → 자동 "
            f"{_fmt(h1.get('automated_avg_sec'))}초 ({_fmt(red, 1)}% 단축, n={h1.get('n', 0)})",
        ),
        "verdict": "insufficient" if red is None else "supported" if red > 0 else "not_supported",
    })

    util, target = h2.get("utilization_avg_pct"), h2.get("target_utilization_pct")
    meets = h2.get("meets_target")
    rows.append({
        "id": "H2",
        "claim": tr("Allocation lowers resource idle time", "자원 배분이 유휴 시간을 줄인다"),
        "evidence": tr(
            f"utilization {_fmt(util, 1)}% vs. target {_fmt(target)}% "
            f"(idle {_fmt(h2.get('idle_avg_pct'), 1)}%)",
            f"활용률 {_fmt(util, 1)}% / 목표 {_fmt(target)}% (유휴 {_fmt(h2.get('idle_avg_pct'), 1)}%)",
        ),
        "verdict": "insufficient" if meets is None else "supported" if meets else "partial",
    })

    f1 = h3.get("f1")
    rows.append({
        "id": "H3",
        "claim": tr("Risks are detected early and accurately",
                    "리스크를 조기에 정확히 탐지한다"),
        "evidence": tr(
            f"precision {_fmt(h3.get('precision'))} · recall {_fmt(h3.get('recall'))} · "
            f"F1 {_fmt(f1)} on {len(h3.get('detail', []))} projects",
            f"정밀도 {_fmt(h3.get('precision'))} · 재현율 {_fmt(h3.get('recall'))} · "
            f"F1 {_fmt(f1)} (프로젝트 {len(h3.get('detail', []))}개)",
        ),
        "verdict": "insufficient" if f1 is None else "supported" if f1 >= 0.7
        else "partial" if f1 >= 0.4 else "not_supported",
    })

    gain = h4.get("coverage_gain")
    rows.append({
        "id": "H4",
        "claim": tr("Lessons learned (A7) back up decisions",
                    "과거 교훈(A7)이 판단 근거를 제공한다"),
        "evidence": tr(f"{_fmt(gain)} citations with A7, 0 without",
                       f"A7 사용 시 인용 {_fmt(gain)}건, 미사용 시 0건"),
        "verdict": "insufficient" if gain is None else "supported" if gain > 0 else "not_supported",
    })

    strata = h5.get("strata") or {}
    low = (strata.get("low") or {}).get("avg_spi")
    high = (strata.get("high") or {}).get("avg_spi")
    rows.append({
        "id": "H5",
        "claim": tr("Portfolio complexity moderates the effect",
                    "포트폴리오 복잡성이 효과를 조절한다"),
        "evidence": tr(f"SPI low-complexity {_fmt(low, 3)} vs. high-complexity {_fmt(high, 3)}",
                       f"SPI 저복잡도 {_fmt(low, 3)} / 고복잡도 {_fmt(high, 3)}"),
        "verdict": "insufficient" if low is None or high is None
        else "supported" if high < low else "not_supported",
    })
    return rows


def kpi_summary() -> list[dict]:
    out = []
    for axis, metric, label in _KPI_ROWS:
        s = metric_summary(metric)
        out.append({"axis": axis, "metric": metric, "label": tr(*label), "count": s["count"],
                    "avg": s["avg"], "sum": s["sum"]})
    return out


def _verdict_label(key: str) -> str:
    en, ko, _ = _VERDICT[key]
    return tr(en, ko)


def _limitations() -> list[str]:
    return [
        tr("Small samples give unstable precision/recall; report n with every number.",
           "표본이 작으면 정밀도·재현율이 불안정합니다. 모든 수치에 n을 함께 보고하세요."),
        tr("LLM outputs are non-deterministic; deterministic fallbacks and schema validation "
           "limit, but do not remove, run-to-run variation.",
           "LLM 출력은 비결정적입니다. 결정론적 폴백과 스키마 검증으로 줄였지만 실행 간 차이는 남습니다."),
        tr("Baselines are only as good as the manual-process measurements behind them.",
           "기준선(baselines)의 신뢰도는 수작업 측정값의 품질에 달려 있습니다."),
    ]


_CALIBRATION = {
    "calibrated": ("Calibrated", "보정됨"),
    "overconfident": ("Overconfident", "과신"),
    "underconfident": ("Underconfident", "과소 확신"),
    "uninformative": ("Uninformative (one confidence value)", "변별력 없음 (확신도 값이 하나)"),
    "insufficient": ("Insufficient data", "데이터 부족"),
}


def _calibration_rows(report: dict) -> list[tuple[str, str, str, str, str, str]]:
    """(source, n, verdict, ECE, Brier, distinct values) for overall and each source."""
    cal = report["results"].get("calibration")
    if not cal:
        return []
    names = {"overall": tr("All", "전체"), "risk_alert": tr("Risk alerts (A4)", "리스크 경보(A4)"),
             "approval": tr("Approval decisions", "승인 결정")}
    blocks = [("overall", cal["overall"]), *cal["by_source"].items()]
    return [(names[k], str(c["n"]), tr(*_CALIBRATION[c["verdict"]]), _fmt(c["ece"]),
             _fmt(c["brier"]), str(c["distinct_confidences"])) for k, c in blocks]


def build_report(results: dict, *, scope: str, source: str) -> dict:
    """Structured report content, shared by the Markdown and HTML renderers."""
    return {
        "title": tr("MA-PMO evaluation report", "MA-PMO 평가 보고서"),
        "scope": scope,
        "source": source,
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC"),
        "version": __version__,
        "lang": get_lang(),
        "summary": summarize(results),
        "kpis": kpi_summary(),
        "results": results,
        "limitations": _limitations(),
    }


def render_markdown(report: dict) -> str:
    L = []
    L.append(f"# {report['title']}")
    L.append("")
    L.append(tr(
        f"- **Scope**: `{report['scope']}`\n- **Data**: {report['source']}\n"
        f"- **Generated**: {report['generated_at']} · MA-PMO {report['version']}",
        f"- **대상**: `{report['scope']}`\n- **데이터**: {report['source']}\n"
        f"- **생성**: {report['generated_at']} · MA-PMO {report['version']}",
    ))
    L.append("")
    L.append(tr("## 1. Summary", "## 1. 요약"))
    L.append("")
    L.append(tr("| Hypothesis | Claim | Evidence | Verdict |", "| 가설 | 내용 | 근거 | 판정 |"))
    L.append("|---|---|---|---|")
    for r in report["summary"]:
        L.append(f"| {r['id']} | {r['claim']} | {r['evidence']} | "
                 f"**{_verdict_label(r['verdict'])}** |")
    L.append("")
    L.append(tr("## 2. Five-axis KPIs", "## 2. 5축 KPI"))
    L.append("")
    L.append(tr("| Axis | Metric | n | Average |", "| 축 | 지표 | n | 평균 |"))
    L.append("|---|---|---|---|")
    for k in report["kpis"]:
        L.append(f"| {k['axis']} | {k['label']} | {k['count']} | {_fmt(k['avg'])} |")
    L.append("")
    L.append(tr("## 3. H3 risk detection detail", "## 3. H3 리스크 탐지 상세"))
    L.append("")
    L.append(tr("| Project | Predicted | Actual |", "| 프로젝트 | 예측 | 실제 |"))
    L.append("|---|---|---|")
    for d in report["results"].get("H3", {}).get("detail", []):
        L.append(f"| {d['project_id']} | {d['predicted']} | {d['actual']} |")
    L.append("")
    L.append(tr("## 4. Confidence calibration", "## 4. 확신도 보정"))
    L.append("")
    L.append(tr("| Source | n | Verdict | ECE | Brier | Distinct values |",
                "| 출처 | n | 판정 | ECE | Brier | 확신도 값 종류 |"))
    L.append("|---|---|---|---|---|---|")
    L += ["| " + " | ".join(row) + " |" for row in _calibration_rows(report)]
    L.append("")
    L.append(tr("## 5. Limitations", "## 5. 한계"))
    L.append("")
    L += [f"- {x}" for x in report["limitations"]]
    L.append("")
    return "\n".join(L)


def render_html(report: dict) -> str:
    e = html.escape
    rows = "".join(
        f"<tr><td class='h'>{e(r['id'])}</td><td>{e(r['claim'])}</td><td>{e(r['evidence'])}</td>"
        f"<td><span class='v' style='background:{_VERDICT[r['verdict']][2]}'>"
        f"{e(_verdict_label(r['verdict']))}</span></td></tr>"
        for r in report["summary"]
    )
    kpis = "".join(
        f"<tr><td>{e(k['axis'])}</td><td>{e(k['label'])}</td><td class='n'>{k['count']}</td>"
        f"<td class='n'>{e(_fmt(k['avg']))}</td></tr>" for k in report["kpis"]
    )
    h3 = "".join(
        f"<tr><td>{e(d['project_id'])}</td><td>{e(d['predicted'])}</td>"
        f"<td>{e(d['actual'])}</td></tr>"
        for d in report["results"].get("H3", {}).get("detail", [])
    )
    cal = "".join("<tr>" + "".join(f"<td>{e(c)}</td>" for c in row) + "</tr>"
                  for row in _calibration_rows(report))
    lim = "".join(f"<li>{e(x)}</li>" for x in report["limitations"])
    labels = {
        "scope": tr("Scope", "대상"), "data": tr("Data", "데이터"),
        "generated": tr("Generated", "생성"),
        "s1": tr("Summary", "요약"), "s2": tr("Five-axis KPIs", "5축 KPI"),
        "s3": tr("H3 risk detection detail", "H3 리스크 탐지 상세"),
        "s4": tr("Confidence calibration", "확신도 보정"),
        "s5": tr("Limitations", "한계"),
        "th4": [tr("Source", "출처"), "n", tr("Verdict", "판정"), "ECE", "Brier",
                tr("Distinct values", "확신도 값 종류")],
        "th1": [tr("Hypothesis", "가설"), tr("Claim", "내용"), tr("Evidence", "근거"),
                tr("Verdict", "판정")],
        "th2": [tr("Axis", "축"), tr("Metric", "지표"), "n", tr("Average", "평균")],
        "th3": [tr("Project", "프로젝트"), tr("Predicted", "예측"), tr("Actual", "실제")],
    }
    th = lambda cols: "".join(f"<th>{e(c)}</th>" for c in cols)  # noqa: E731
    return f"""<!doctype html>
<html lang="{e(report['lang'])}"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(report['title'])}</title>
<style>
:root{{--fg:#1f2328;--muted:#59636e;--line:#d1d9e0;--bg:#fff;--card:#f6f8fa}}
@media (prefers-color-scheme:dark){{:root{{--fg:#e6edf3;--muted:#9198a1;--line:#3d444d;--bg:#0d1117;--card:#151b23}}}}
body{{margin:0;background:var(--bg);color:var(--fg);
  font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI","Apple SD Gothic Neo",sans-serif}}
main{{max-width:960px;margin:0 auto;padding:40px 20px}}
h1{{margin:0 0 8px;font-size:28px}} h2{{margin:36px 0 12px;font-size:19px}}
.meta{{color:var(--muted);font-size:13px}} .meta b{{color:var(--fg)}}
table{{width:100%;border-collapse:collapse;background:var(--card);border-radius:10px;overflow:hidden}}
th,td{{text-align:left;padding:10px 12px;border-bottom:1px solid var(--line);vertical-align:top}}
th{{font-size:12px;text-transform:uppercase;letter-spacing:.04em;color:var(--muted)}}
td.h{{font-weight:700}} td.n{{text-align:right;font-variant-numeric:tabular-nums}}
.v{{color:#fff;border-radius:999px;padding:2px 10px;font-size:12px;font-weight:600;white-space:nowrap}}
ul{{padding-left:20px}} footer{{margin-top:40px;color:var(--muted);font-size:12px}}
</style></head><body><main>
<h1>{e(report['title'])}</h1>
<div class="meta"><b>{labels['scope']}</b> {e(report['scope'])} · <b>{labels['data']}</b>
{e(report['source'])} · <b>{labels['generated']}</b> {e(report['generated_at'])}</div>
<h2>1. {labels['s1']}</h2><table><tr>{th(labels['th1'])}</tr>{rows}</table>
<h2>2. {labels['s2']}</h2><table><tr>{th(labels['th2'])}</tr>{kpis}</table>
<h2>3. {labels['s3']}</h2><table><tr>{th(labels['th3'])}</tr>{h3}</table>
<h2>4. {labels['s4']}</h2><table><tr>{th(labels['th4'])}</tr>{cal}</table>
<h2>5. {labels['s5']}</h2><ul>{lim}</ul>
<footer>MA-PMO {e(report['version'])} · github.com/ma-pmo/ma-pmo-ext</footer>
</main></body></html>
"""


def render(report: dict, fmt: str = "md") -> str:
    if fmt == "html":
        return render_html(report)
    if fmt in ("md", "markdown"):
        return render_markdown(report)
    raise ValueError(f"unknown report format: {fmt} (use md or html)")
