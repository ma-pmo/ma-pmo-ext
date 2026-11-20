"use client";
// Reports A5 wrote: pick one to read it as the server renders it (the same HTML a download
// gives), see what changed since the last report, download it, or write a new one.
import { useEffect, useRef, useState } from "react";
import { api, errorText } from "../lib/api";
import { useI18n } from "../lib/i18n";
import { when } from "../lib/time";
import { Card, PageHeader, ErrorCard } from "../components/shell";
import { Icon } from "../components/icons";

type Row = {
  id: string; scope: string; kind: string; title: string; as_of: string; overall_status: string;
  path: "llm" | "rule"; projects: string[] | null; created_at: string;
};
type Full = { id: string; insights: { severity: string }[]; grounding: { replaced: boolean } | null; path: string };

const KINDS = ["status", "executive", "exception", "gate", "closure"];
const MAKERS = ["weekly_status", "executive_briefing", "risk_escalation", "go_nogo_decision",
  "lessons_learned_closure"];
const FORMATS = ["html", "md", "csv", "json", "docx"];

export default function Reports() {
  const { lang, t } = useI18n();
  const r = t.reports;
  const [kind, setKind] = useState("");
  const [rows, setRows] = useState<Row[] | null>(null);
  const [picked, setPicked] = useState("");
  const [full, setFull] = useState<Full | null>(null);
  const [html, setHtml] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState("");
  const [note, setNote] = useState("");
  const frame = useRef<HTMLIFrameElement>(null);

  const load = async (select?: string) => {
    try {
      const list: Row[] = await api.reports(kind || undefined);
      setRows(list); setErr("");
      const want = select ?? (new URLSearchParams(window.location.search).get("id") || picked);
      setPicked(list.some((x) => x.id === want) ? want : list[0]?.id ?? "");
    } catch (e) { setErr(errorText(e)); }
  };
  useEffect(() => { load(); }, [kind, lang]);  // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!picked) { setHtml(""); setFull(null); return; }
    api.report(picked).then(setFull).catch(() => setFull(null));
    api.reportExport(picked, "html").then((res) => res.text()).then(setHtml)
      .catch((e) => setErr(errorText(e)));
  }, [picked, lang]);

  const make = async (workflow: string) => {
    setBusy(workflow); setNote("");
    try {
      await api.runScenario(workflow);
      const list: Row[] = await api.reports(kind || undefined);
      setRows(list);
      if (list[0]) { setPicked(list[0].id); setNote(r.made(list[0].id)); }
    } catch (e) { setErr(errorText(e)); } finally { setBusy(""); }
  };

  const download = async (format: string) => {
    const res = await api.reportExport(picked, format);
    const name = /filename="([^"]+)"/.exec(res.headers.get("content-disposition") || "")?.[1]
      || `${picked}.${format}`;
    const url = URL.createObjectURL(await res.blob());
    const a = Object.assign(document.createElement("a"), { href: url, download: name });
    a.click();
    URL.revokeObjectURL(url);
  };

  const row = rows?.find((x) => x.id === picked);
  const writer = (x: Row) => x.path === "llm" ? r.llm
    : full?.id === x.id && full.grounding?.replaced ? r.replaced : r.rule;
  const changes = full?.insights.filter((i) => i.severity !== "low").length ?? 0;

  return (
    <div className="stack">
      <PageHeader title={t.nav.reports} desc={t.pages.reports} actions={
        <label className="row" style={{ gap: 6 }}>
          <span className="muted">{r.kind}</span>
          <select className="input" value={kind} onChange={(e) => setKind(e.target.value)}>
            <option value="">{r.all}</option>
            {KINDS.map((k) => <option key={k} value={k}>{r.kinds[k]}</option>)}
          </select>
        </label>
      } />
      {err && <ErrorCard label={t.common.error}>{err}</ErrorCard>}
      <Card title={r.make}>
        <div className="row" style={{ flexWrap: "wrap", gap: 8 }}>
          {MAKERS.map((w) => (
            <button key={w} className="ghost" disabled={!!busy} onClick={() => make(w)}>
              {busy === w ? r.making : r.workflows[w]}
            </button>
          ))}
          {note && <span role="status" className="badge green">{note}</span>}
        </div>
      </Card>
      {rows && rows.length === 0 && <Card><p className="muted" style={{ margin: 0 }}>{r.none}</p></Card>}
      {rows && rows.length > 0 && (
        <div className="reports-layout">
          <Card flush>
            <ul className="report-list" aria-label={t.nav.reports}>
              {rows.map((x) => (
                <li key={x.id}>
                  <button className={x.id === picked ? "on" : ""} aria-current={x.id === picked}
                    onClick={() => setPicked(x.id)}>
                    <span className="row" style={{ gap: 6, justifyContent: "space-between" }}>
                      <b>{r.kinds[x.kind] ?? x.kind}</b>
                      <span className={`badge ${x.overall_status}`}>{x.overall_status}</span>
                    </span>
                    <span className="muted">{x.as_of} · {x.projects ? r.projects(x.projects) : x.scope}</span>
                    <span className="muted small"><code>{x.id}</code> · {when(x.created_at, lang)}</span>
                  </button>
                </li>
              ))}
            </ul>
          </Card>
          {row ? (
            <Card title={row.title || r.kinds[row.kind]} desc={
              <>{r.asOf} {row.as_of} · {r.writer}: {writer(row)}{changes > 0 && <> · {r.changes(changes)}</>}</>
            } actions={
              <div className="row" style={{ gap: 6, flexWrap: "wrap" }}>
                {FORMATS.map((f) => (
                  <button key={f} className="ghost" onClick={() => download(f)} aria-label={`${r.download} ${f}`}>
                    <Icon.download /> {f === "docx" ? "Word" : f.toUpperCase()}
                  </button>
                ))}
                <button className="ghost" onClick={() => frame.current?.contentWindow?.print()}>{r.print}</button>
              </div>
            }>
              <iframe ref={frame} className="report-frame" title={row.title || row.id} srcDoc={html} />
            </Card>
          ) : <Card><p className="muted">{r.pick}</p></Card>}
        </div>
      )}
    </div>
  );
}
