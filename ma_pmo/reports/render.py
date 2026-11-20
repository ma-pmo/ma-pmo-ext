"""A stored report as Markdown, HTML (print it to PDF from the browser), CSV, JSON or Word.

    ma-pmo report export RPT-1a2b3c4d --format html --out report.html
    GET /reports/{id}/export?format=md|html|csv|json|docx

Word (`docx`) needs the extra: pip install "ma-pmo[export]".

The sections and their order come from the report's kind (`reports/kinds.py`). Numbers come
from the computed facts; only the summary, risks and actions are the narrative.
"""
from __future__ import annotations

import csv
import html
import io
import json
from dataclasses import dataclass, field
from typing import Any

from ma_pmo import __version__
from ma_pmo.core.i18n import tr, use_lang
from ma_pmo.core.schemas.payloads.report_v2 import ReportV2
from ma_pmo.reports import kinds

FORMATS = ("md", "html", "csv", "json", "docx")
MEDIA = {"md": "text/markdown; charset=utf-8", "html": "text/html; charset=utf-8",
         "csv": "text/csv; charset=utf-8", "json": "application/json",
         "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}
_RAG = {"green": "#1a7f37", "amber": "#9a6700", "red": "#cf222e"}


@dataclass
class Section:
    heading: str
    text: str = ""
    table: tuple[list[str], list[list[str]]] | None = None
    items: list[str] = field(default_factory=list)
    ordered: bool = False


def _num(v: float | None, unit: str = "") -> str:
    if v is None:
        return "–"
    s = f"{v:.3f}".rstrip("0").rstrip(".") if v != int(v) else str(int(v))
    return f"{s}{unit}" if unit in ("%", "", "일") else f"{s} {unit}"


def _change(delta: float | None, better: str) -> str:
    if delta is None or delta == 0:
        return "–" if delta is None else "="
    good = (delta > 0) == (better == "higher")
    verdict = tr("better", "개선") if good else tr("worse", "악화")
    return f"{'▲' if delta > 0 else '▼'} {_num(abs(delta))} ({verdict})"


def _late(days: float) -> str:
    if days > 0:
        return tr(f"{_num(days)} late", f"{_num(days)}일 늦음")
    if days < 0:
        return tr(f"{_num(-days)} early", f"{_num(-days)}일 여유")
    return tr("on time", "정시")


def _clip(text: str, n: int = 160) -> str:
    text = " ".join(text.split())
    return text if len(text) <= n else text[:n].rsplit(" ", 1)[0] + " …"


def _status(now: str, before: str | None) -> str:
    return now if before in (None, now) else f"{before} → {now}"


def sections(r: ReportV2) -> list[Section]:
    f = r.facts
    out: dict[str, Section] = {}
    out["summary"] = Section(tr("Summary", "요약"), text=r.executive_summary)
    marks = {"high": "▲▲", "medium": "▲", "low": "▽"}
    out["changes"] = Section(tr("Since the last report", "직전 보고 이후"), items=[
        f"{marks[i.severity]} {i.text} → {i.action}" for i in r.insights
    ] or [tr("Nothing to compare yet: this is the first report of its kind for this scope.",
             "아직 비교할 보고서가 없습니다. 이 범위·종류의 첫 보고서입니다.")
          if not r.facts.previous_report_id else
          tr("No change worth reporting.", "보고할 만한 변화가 없습니다.")])
    out["kpis"] = Section(tr("Key figures", "핵심 지표"), table=(
        [tr("Measure", "지표"), tr("Now", "현재"), tr("Last report", "직전 보고"),
         tr("Change", "변화")],
        [[k.label, _num(k.value, k.unit), _num(k.previous, k.unit), _change(k.delta, k.better)]
         for k in f.kpis]))
    out["projects"] = Section(tr("Projects", "프로젝트"), table=(
        [tr("Project", "프로젝트"), tr("Status", "상태"), tr("Progress", "진척"), "SPI",
         tr("Deadline", "마감"), tr("Forecast", "예상 완료"), tr("Slack (days)", "여유(일)")],
        [[p.project_id, _status(p.status, p.previous_status),
          _num(p.percent_complete, "%") + (
              f" ({p.percent_complete - p.previous_percent_complete:+g})"
              if p.previous_percent_complete is not None else ""),
          _num(p.spi), p.deadline or "–", p.forecast_finish or tr("done", "완료"),
          _num(p.slack_days)] for p in f.projects]))
    breached = {t.project_id for t in f.breaches}
    flagged = [p for p in f.projects if p.status != "green" or p.project_id in breached]
    out["exceptions"] = Section(tr("Exceptions", "예외"), items=[
        tr(f"**{p.project_id}** {p.status}: forecast {p.forecast_finish or 'done'} against "
           f"deadline {p.deadline or '–'} (slack {_num(p.slack_days)} days), SPI {_num(p.spi)}",
           f"**{p.project_id}** {p.status}: 예상 완료 {p.forecast_finish or '완료'}, 마감 "
           f"{p.deadline or '–'}(여유 {_num(p.slack_days)}일), SPI {_num(p.spi)}")
        for p in flagged] or [tr("None: every project is green and within tolerance.",
                                 "없음: 모든 프로젝트가 green이고 허용 범위 안입니다.")])
    out["tolerances"] = Section(tr("Tolerances", "허용 범위"), table=(
        [tr("Project", "프로젝트"), tr("Measure", "기준"), tr("Value", "값"),
         tr("Limit", "한도"), tr("Within", "범위 안")],
        [[t.project_id, tr("Forecast vs deadline (days)", "예상 완료 − 마감(일)")
          if t.dimension == "schedule" else "SPI",
          _late(t.value) if t.dimension == "schedule" else _num(t.value),
          (tr(f"≤ {_num(t.limit)} late", f"지연 {_num(t.limit)}일 이하")
           if t.dimension == "schedule" else f"≥ {_num(t.limit)}"),
          "✓" if not t.breached else "✗"] for t in f.tolerances]))
    if f.risks:
        out["risks"] = Section(tr("Risks", "리스크"), table=(
            [tr("Project", "프로젝트"), tr("Severity", "심각도"), tr("Signal", "신호"),
             tr("Mitigation", "대응")],
            [[x.project_id, x.severity, x.signal, x.mitigation] for x in f.risks]))
    else:
        out["risks"] = Section(tr("Risks", "리스크"), items=r.key_risks or [tr("None", "없음")])
    rows = [[g.project_id, tr(f"gate {g.gate}", f"게이트 {g.gate}"), g.decision,
             ", ".join(g.failed) or "–", "; ".join(g.conditions) or "–"] for g in f.gates]
    rows += [[a.project_id or a.task_ref, tr(f"approval #{a.approval_id} ({a.schema_})",
                                             f"승인 #{a.approval_id} ({a.schema_})"),
              tr("waiting", "대기"), "–",
              tr("held by review", "검토가 보류") if a.held_by_review
              else tr("approval required", "승인 필요")] for a in f.approvals]
    out["decisions"] = Section(tr("Decisions needed", "필요한 결정"), table=(
        [tr("Project", "프로젝트"), tr("Item", "항목"), tr("Decision", "결정"),
         tr("Failed criteria", "미충족 기준"), tr("Conditions / why", "조건·사유")], rows)
    ) if rows else Section(tr("Decisions needed", "필요한 결정"), text=tr(
        "No gate decisions in this run and nothing waiting for approval.",
        "이 실행에 게이트 결정이 없고 승인 대기 항목도 없습니다."))
    out["lessons"] = Section(tr("Lessons", "교훈"), items=[
        f"{x.source_id}: {_clip(x.excerpt)}" for x in f.lessons] or [tr("None cited", "인용 없음")])
    out["actions"] = Section(tr("Recommended actions", "권고 조치"),
                             items=r.recommended_actions or [tr("None", "없음")], ordered=True)
    return [out[name] for name in kinds.spec(r.kind).sections]


def _header(r: ReportV2, report_id: str) -> list[tuple[str, str]]:
    f = r.facts
    period = f"{f.period_start} – {f.as_of}" if f.period_start else f.as_of
    rows = [(tr("Scope", "범위"), r.scope + (f" ({', '.join(f.projects_in_scope)})"
                                           if f.projects_in_scope else "")),
            (tr("Period", "기간"), period),
            (tr("Overall", "종합"), r.overall_status),
            (tr("For", "대상"), tr("executives", "경영진") if r.audience == "executive"
             else tr("team", "팀")),
            (tr("Report", "보고서"), report_id)]
    return rows


def _footer(r: ReportV2) -> str:
    who = tr("an LLM", "LLM") if r.path == "llm" else tr("rules (no LLM)", "규칙(LLM 없음)")
    text = tr(f"Figures are computed by MA-PMO {__version__} from the tracker and the agents' "
              f"posts; the summary, risks and actions were written by {who}.",
              f"수치는 트래커와 에이전트 게시물을 바탕으로 MA-PMO {__version__}에서 계산했고, "
              f"요약·리스크·조치는 {who}이 작성했습니다.")
    g = r.grounding
    if g and g.replaced:
        text += " " + tr(f"The LLM's text cited figures not in the facts "
                         f"({', '.join(g.ungrounded[:5])}) and was replaced.",
                         f"LLM 문장에 사실에 없는 수치({', '.join(g.ungrounded[:5])})가 있어 "
                         f"교체했습니다.")
    elif g:
        text += " " + tr(f"All {g.checked} figures, dates and ids in it match the facts.",
                         f"문장 속 수치·날짜·id {g.checked}개가 모두 사실과 일치합니다.")
    return text


def to_markdown(r: ReportV2, report_id: str) -> str:
    lines = [f"# {r.title or kinds.title(r.kind)}", ""]
    lines += [f"- **{k}:** {v}" for k, v in _header(r, report_id)] + [""]
    for s in sections(r):
        lines += [f"## {s.heading}", ""]
        if s.text:
            lines += [s.text, ""]
        if s.table:
            head, rows = s.table
            lines += ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
            lines += ["| " + " | ".join(c.replace("|", "\\|") for c in row) + " |" for row in rows]
            lines.append("")
        if s.items:
            lines += [f"{i}. {x}" if s.ordered else f"- {x}" for i, x in enumerate(s.items, 1)]
            lines.append("")
    lines += ["---", "", f"*{_footer(r)}*", ""]
    return "\n".join(lines)


def _inline(text: str) -> str:
    """Escape, then turn **bold** back into <strong>."""
    parts = html.escape(text).split("**")
    return "".join(f"<strong>{p}</strong>" if i % 2 else p for i, p in enumerate(parts))


def to_html(r: ReportV2, report_id: str) -> str:
    e = html.escape
    lang = r.language if r.language in ("en", "ko") else "en"
    body = [f"<h1>{e(r.title or kinds.title(r.kind))}</h1>", "<dl>"]
    for k, v in _header(r, report_id):
        cell = (f'<span class="rag" style="background:{_RAG[v]}">{e(v)}</span>'
                if v in _RAG else e(v))
        body.append(f"<dt>{e(k)}</dt><dd>{cell}</dd>")
    body.append("</dl>")
    for s in sections(r):
        body.append(f"<h2>{e(s.heading)}</h2>")
        if s.text:
            body.append(f"<p>{_inline(s.text)}</p>")
        if s.table:
            head, rows = s.table
            body.append("<table><thead><tr>" + "".join(f"<th>{e(h)}</th>" for h in head)
                        + "</tr></thead><tbody>")
            body += ["<tr>" + "".join(f"<td>{e(c)}</td>" for c in row) + "</tr>" for row in rows]
            body.append("</tbody></table>")
        if s.items:
            tag = "ol" if s.ordered else "ul"
            body.append(f"<{tag}>" + "".join(f"<li>{_inline(x)}</li>" for x in s.items)
                        + f"</{tag}>")
    body.append(f'<p class="foot">{e(_footer(r))}</p>')
    style = ("body{font-family:system-ui,sans-serif;max-width:900px;margin:2rem auto;"
             "padding:0 1rem;color:#1f2328}table{border-collapse:collapse;width:100%;"
             "margin:.5rem 0 1rem}th,td{border:1px solid #d0d7de;padding:.35rem .5rem;"
             "text-align:left;font-size:.9rem}th{background:#f6f8fa}dl{display:grid;"
             "grid-template-columns:max-content 1fr;gap:.2rem 1rem}dt{font-weight:600}"
             "dd{margin:0}.rag{color:#fff;padding:0 .5rem;border-radius:4px}"
             ".foot{color:#656d76;font-size:.8rem;margin-top:2rem}"
             "@media print{body{margin:0;max-width:none}}")
    return (f'<!doctype html><html lang="{lang}"><head><meta charset="utf-8">'
            f"<title>{e(r.title or kinds.title(r.kind))} · {e(r.scope)} · {e(r.facts.as_of)}"
            f"</title><style>{style}</style></head><body>{''.join(body)}</body></html>")


def to_csv(r: ReportV2, report_id: str) -> str:
    """One row per project, for spreadsheets."""
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["report_id", "kind", "scope", "as_of", "project_id", "status", "previous_status",
                "percent_complete", "previous_percent_complete", "spi", "deadline",
                "forecast_finish", "slack_days", "breaches"])
    breaches: dict[str, list[str]] = {}
    for t in r.facts.breaches:
        breaches.setdefault(t.project_id, []).append(t.dimension)
    for p in r.facts.projects:
        w.writerow([report_id, r.kind, r.scope, r.facts.as_of, p.project_id, p.status,
                    p.previous_status or "", p.percent_complete,
                    "" if p.previous_percent_complete is None else p.previous_percent_complete,
                    "" if p.spi is None else p.spi, p.deadline or "", p.forecast_finish or "",
                    "" if p.slack_days is None else p.slack_days,
                    ";".join(breaches.get(p.project_id, []))])
    return buf.getvalue()


def to_docx(r: ReportV2, report_id: str) -> bytes:
    """The report as a Word document, with the same sections and tables as the HTML."""
    try:
        import docx
        from docx.oxml.ns import qn
        from docx.shared import Pt, RGBColor
    except ImportError as e:  # optional dependency
        raise ImportError('Word export needs the extra: pip install "ma-pmo[export]"') from e

    d = docx.Document()
    normal = d.styles["Normal"]
    normal.font.size = Pt(10)  # and a font for Korean text:
    normal.element.get_or_add_rPr().get_or_add_rFonts().set(qn("w:eastAsia"), "Malgun Gothic")

    def text(paragraph: Any, value: str) -> None:  # **bold** as in the Markdown
        for i, part in enumerate(value.split("**")):
            paragraph.add_run(part).bold = i % 2 == 1

    d.add_heading(r.title or kinds.title(r.kind), 0)
    head = d.add_table(rows=0, cols=2)
    for k, v in _header(r, report_id):
        cells = head.add_row().cells
        cells[0].text, cells[1].text = k, v
        cells[0].paragraphs[0].runs[0].bold = True
        if v in _RAG:
            cells[1].paragraphs[0].runs[0].font.color.rgb = RGBColor.from_string(_RAG[v][1:])
    for s in sections(r):
        d.add_heading(s.heading, 1)
        if s.text:
            text(d.add_paragraph(), s.text)
        if s.table:
            columns, rows = s.table
            t = d.add_table(rows=1, cols=len(columns))
            t.style = "Table Grid"  # in every Word template, and shown by every viewer
            for cell, name in zip(t.rows[0].cells, columns, strict=True):
                cell.text = name
                cell.paragraphs[0].runs[0].bold = True
            for row in rows:
                for cell, value in zip(t.add_row().cells, row, strict=True):
                    cell.text = value
        for item in s.items:
            text(d.add_paragraph(style="List Number" if s.ordered else "List Bullet"), item)
    foot = d.add_paragraph().add_run(_footer(r))
    foot.italic, foot.font.size = True, Pt(8)
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()


def render_bytes(content: dict[str, Any], report_id: str, fmt: str) -> bytes:
    """Like `render`, as bytes; the only way to get `docx`."""
    if fmt != "docx":
        return render(content, report_id, fmt).encode("utf-8")
    r = ReportV2.model_validate(content)
    with use_lang(r.language):
        return to_docx(r, report_id)


def render(content: dict[str, Any], report_id: str, fmt: str) -> str:
    """A stored report's content in `fmt` (md, html, csv, json), in the report's language."""
    if fmt not in FORMATS or fmt == "docx":
        raise ValueError(f"format must be one of {', '.join(f for f in FORMATS if f != 'docx')}")
    if fmt == "json":
        return json.dumps({"id": report_id, **content}, ensure_ascii=False, indent=2)
    r = ReportV2.model_validate(content)
    with use_lang(r.language):
        return {"md": to_markdown, "html": to_html, "csv": to_csv}[fmt](r, report_id)
