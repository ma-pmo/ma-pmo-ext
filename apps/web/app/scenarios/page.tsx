"use client";
import { useEffect, useRef, useState } from "react";
import { api } from "../lib/api";
import { useI18n } from "../lib/i18n";
import { Card, PageHeader } from "../components/shell";

const PHASE_META: Record<string, { num: string; icon: string; color: string }> = {
  plan: { num: "①", icon: "🧭", color: "var(--accent)" },
  execute: { num: "②", icon: "⚙️", color: "var(--amber)" },
  complete: { num: "③", icon: "✅", color: "var(--green)" },
  insight: { num: "④", icon: "💡", color: "var(--purple)" },
};

export default function Scenarios() {
  const { lang, t } = useI18n();
  const c = t.scn;
  const [scenarios, setScenarios] = useState<any[]>([]);
  const [category, setCategory] = useState("all");
  const [selected, setSelected] = useState<string>("");
  const [trace, setTrace] = useState<any>(null);
  const [running, setRunning] = useState(false);
  const [err, setErr] = useState("");
  const [showPaper, setShowPaper] = useState(false);
  const [copied, setCopied] = useState(false);
  const traceRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setTrace(null);
    api.scenarios().then(setScenarios).catch((e) => setErr(String(e.message || e)));
  }, [lang]);

  async function run(id: string) {
    setSelected(id);
    setRunning(true);
    setErr("");
    setTrace(null);
    try {
      setTrace(await api.runScenario(id));
      setTimeout(() => traceRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }), 50);
    } catch (e: any) {
      setErr(String(e.message || e));
    } finally {
      setRunning(false);
    }
  }

  const categories = [...new Map(scenarios.map((s) => [s.category_id, s.category])).entries()];
  const shown = category === "all" ? scenarios : scenarios.filter((s) => s.category_id === category);

  return (
    <div className="stack">
      <PageHeader title={c.title} desc={t.pages.scenarios} />
      {err && <div className="card" style={{ color: "var(--red)" }}>{t.common.error}: {err}</div>}

      <div>
        <div className="tabs" role="tablist">
          <button className={category === "all" ? "on" : ""} onClick={() => setCategory("all")}>
            {t.common2.all} <span className="n">{scenarios.length}</span>
          </button>
          {categories.map(([id, label]) => (
            <button key={id} className={category === id ? "on" : ""} onClick={() => setCategory(id)}>
              {label} <span className="n">{scenarios.filter((s) => s.category_id === id).length}</span>
            </button>
          ))}
        </div>
        <div className="grid cols-3">
          {shown.map((s) => (
            <div key={s.id} className="card" style={{ borderColor: selected === s.id ? "var(--accent)" : undefined, display: "flex", flexDirection: "column", gap: 8 }}>
              <div className="row" style={{ justifyContent: "space-between" }}>
                <span className="badge">{s.category}</span>
                <span className="muted">{c.hypotheses}: {s.hypotheses.join(", ")}</span>
              </div>
              <h2>{s.title}</h2>
              <div className="muted" style={{ flex: 1 }}>{s.description}</div>
              <div className="row" style={{ justifyContent: "space-between" }}>
                <div className="row">{s.agents.map((a: string, i: number) => <span key={i} className="badge accent">{a}</span>)}</div>
                <button className="sm" onClick={() => run(s.id)} disabled={running && selected === s.id}>
                  {running && selected === s.id ? t.common.running : c.runScenario}
                </button>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* run trace (four-phase timeline) */}
      {trace && (
        <div ref={traceRef} style={{ scrollMarginTop: 72 }}>
          <Card
            title={trace.title}
            desc={`${trace.scope} · ${c.hypotheses} ${trace.hypotheses.join(", ")}`}
            actions={
              <div className="row">
                <a className="btn ghost sm"
                  href={`/workflows?id=${encodeURIComponent(trace.scenario_id)}&run=${encodeURIComponent(trace.run_id)}`}>
                  {c.openInWorkflow}
                </a>
                {trace.paper_markdown && (
                  <button className="ghost sm" onClick={() => setShowPaper((v) => !v)}>{c.paperToggle(showPaper)}</button>
                )}
              </div>
            }
          >
            {showPaper && trace.paper_markdown && (
              <div style={{ marginBottom: 16 }}>
                <div className="row" style={{ justifyContent: "space-between", marginBottom: 8 }}>
                  <b>{c.paperTitle}</b>
                  <button className="sm" onClick={() => {
                    navigator.clipboard.writeText(trace.paper_markdown);
                    setCopied(true);
                    setTimeout(() => setCopied(false), 1500);
                  }}>{copied ? c.copied : c.copy}</button>
                </div>
                <pre className="code">{trace.paper_markdown}</pre>
              </div>
            )}
            <div className="timeline">
              {trace.phases.map((p: any, i: number) => {
                const m = PHASE_META[p.phase];
                return (
                  <div key={i} style={{ borderLeftColor: m.color }}>
                    <div style={{ fontWeight: 700, color: m.color }}>{m.icon} {m.num} {p.title}</div>
                    {p.phase === "plan" && (
                      <div style={{ marginTop: 6 }}>
                        <div className="muted">{p.detail}</div>
                        <div className="row" style={{ marginTop: 6 }}>
                          {p.delegations.map((d: any) => <span key={d.agent} className="badge green">{d.agent} {d.function}</span>)}
                        </div>
                      </div>
                    )}
                    {p.phase === "execute" && (
                      <div style={{ marginTop: 6 }}>
                        <span className="muted">{c.outputs(p.elapsed_ms, p.results.length)}</span>
                        <ul style={{ margin: "6px 0", paddingLeft: 18 }}>
                          {p.results.map((r: any, j: number) => (
                            <li key={j}><code>{r.schema}</code> — {r.headline}</li>
                          ))}
                        </ul>
                      </div>
                    )}
                    {p.phase === "complete" && <div className="muted" style={{ marginTop: 6 }}>{p.summary}</div>}
                    {p.phase === "insight" && (
                      <div style={{ marginTop: 6 }}>
                        {p.findings.map((f: any, j: number) => (
                          <div key={j} className="row" style={{ marginBottom: 6 }}>
                            <span className="badge amber">{f.hypothesis}</span>
                            <span className="muted">[{f.axis}]</span>
                            <span>{f.finding}</span>
                          </div>
                        ))}
                        {Object.keys(p.kpi_delta || {}).length > 0 && (
                          <div className="muted" style={{ marginTop: 8, fontSize: 12 }}>
                            {c.kpiNew}: {Object.entries(p.kpi_delta).map(([k, v]: any) => `${k}(+${v.new_events}, avg ${v.avg})`).join(" · ")}
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>

            {trace.communications?.length > 0 && (
              <>
                <h2 style={{ margin: "16px 0 10px" }}>{c.messagesTitle}</h2>
                <div className="table-wrap">
                  <table>
                    <thead><tr><th>{t.common.time}</th><th>{t.common.senderReceiver}</th><th>intent</th><th>schema</th><th className="num">conf.</th><th>HITL</th></tr></thead>
                    <tbody>
                      {trace.communications.map((m: any) => (
                        <tr key={m.message_id}>
                          <td className="muted">{m.timestamp?.slice(11, 19)}</td>
                          <td><span className="badge accent">{m.sender} → {m.receiver}</span></td>
                          <td>{m.intent}</td>
                          <td><code>{m.schema}</code></td>
                          <td className="num muted">{m.confidence}</td>
                          <td>{m.human_gate_required ? <span className="badge red">{t.common.approvalNeeded}</span> : "—"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <div className="muted" style={{ marginTop: 8 }}>{t.common.auditFooter} <code>GET /messages</code></div>
              </>
            )}
          </Card>
        </div>
      )}
    </div>
  );
}
