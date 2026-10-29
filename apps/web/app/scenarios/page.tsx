"use client";
import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { useI18n } from "../lib/i18n";

const PHASE_META: Record<string, { num: string; icon: string; color: string }> = {
  plan: { num: "①", icon: "🧭", color: "var(--accent)" },
  execute: { num: "②", icon: "⚙️", color: "var(--amber)" },
  complete: { num: "③", icon: "✅", color: "var(--green)" },
  insight: { num: "④", icon: "💡", color: "#a371f7" },
};

export default function Scenarios() {
  const { lang, t } = useI18n();
  const c = t.scn;
  const [scenarios, setScenarios] = useState<any[]>([]);
  const [selected, setSelected] = useState<string>("");
  const [trace, setTrace] = useState<any>(null);
  const [running, setRunning] = useState(false);
  const [err, setErr] = useState("");
  const [showPaper, setShowPaper] = useState(false);
  const [copied, setCopied] = useState(false);

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
    } catch (e: any) {
      setErr(String(e.message || e));
    } finally {
      setRunning(false);
    }
  }

  return (
    <main className="grid" style={{ gap: 20 }}>
      <div>
        <h1>{c.title}</h1>
        <p className="muted">
          {c.intro1}<b>{c.phasesBold}</b>{c.intro2}
        </p>
      </div>
      {err && <div className="card" style={{ color: "var(--red)" }}>{t.common.error}: {err}</div>}
      <div className="muted">{c.count(scenarios.length)}</div>

      {/* scenario cards grouped by category */}
      {[...new Set(scenarios.map((s) => s.category_id))].map((cat) => (
        <div key={cat}>
          <h2 style={{ marginBottom: 10 }}>{scenarios.find((s) => s.category_id === cat)?.category}</h2>
          <div className="grid cols-3">
            {scenarios.filter((s) => s.category_id === cat).map((s) => (
              <div
                key={s.id}
                className="card"
                style={{ borderColor: selected === s.id ? "var(--accent)" : "var(--border)", cursor: "pointer" }}
                onClick={() => run(s.id)}
              >
                <h2 style={{ marginBottom: 6, fontSize: 15 }}>{s.title}</h2>
                <div className="muted" style={{ minHeight: 52, fontSize: 13 }}>{s.description}</div>
                <div style={{ marginTop: 8 }}>
                  {s.agents.map((a: string, i: number) => (
                    <span key={i} className="badge" style={{ background: "rgba(88,166,255,.15)", color: "var(--accent)", marginRight: 4 }}>{a}</span>
                  ))}
                </div>
                <div className="muted" style={{ marginTop: 8, fontSize: 12 }}>
                  {c.hypotheses}: {s.hypotheses.join(", ")}
                </div>
                <button style={{ marginTop: 12 }} disabled={running && selected === s.id}>
                  {running && selected === s.id ? t.common.running : c.runScenario}
                </button>
              </div>
            ))}
          </div>
        </div>
      ))}

      {/* run trace (four-phase timeline) */}
      {trace && (
        <div className="card">
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <h2 style={{ margin: 0 }}>
              {trace.title} <span className="muted">· {trace.scope} · {c.hypotheses} {trace.hypotheses.join(", ")}</span>
            </h2>
            {trace.paper_markdown && (
              <button className="ghost" onClick={() => setShowPaper((v) => !v)}>
                {c.paperToggle(showPaper)}
              </button>
            )}
          </div>

          {/* paper-ready Markdown */}
          {showPaper && trace.paper_markdown && (
            <div className="card" style={{ margin: "12px 0", background: "#0b0e14" }}>
              <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 8 }}>
                <strong>{c.paperTitle}</strong>
                <button
                  onClick={() => {
                    navigator.clipboard.writeText(trace.paper_markdown);
                    setCopied(true);
                    setTimeout(() => setCopied(false), 1500);
                  }}
                >
                  {copied ? c.copied : c.copy}
                </button>
              </div>
              <pre style={{ overflowX: "auto", fontSize: 12, whiteSpace: "pre-wrap", margin: 0 }}>
                {trace.paper_markdown}
              </pre>
            </div>
          )}
          <div className="grid" style={{ gap: 12, marginTop: 12 }}>
            {trace.phases.map((p: any, i: number) => {
              const m = PHASE_META[p.phase];
              return (
                <div key={i} style={{ borderLeft: `3px solid ${m.color}`, paddingLeft: 14 }}>
                  <div style={{ fontWeight: 700, color: m.color }}>
                    {m.icon} {m.num} {p.title}
                  </div>

                  {/* plan */}
                  {p.phase === "plan" && (
                    <div style={{ marginTop: 6 }}>
                      <div className="muted">{p.detail}</div>
                      <div style={{ marginTop: 6 }}>
                        {p.delegations.map((d: any) => (
                          <span key={d.agent} className="badge green" style={{ marginRight: 6 }}>
                            {d.agent} {d.function}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* execute */}
                  {p.phase === "execute" && (
                    <div style={{ marginTop: 6 }}>
                      <span className="muted">{c.outputs(p.elapsed_ms, p.results.length)}</span>
                      <ul style={{ margin: "6px 0" }}>
                        {p.results.map((r: any, j: number) => (
                          <li key={j} style={{ fontSize: 13 }}>
                            <code>{r.schema}</code> — {r.headline}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {/* complete */}
                  {p.phase === "complete" && (
                    <div className="muted" style={{ marginTop: 6, fontSize: 13 }}>{p.summary}</div>
                  )}

                  {/* insight */}
                  {p.phase === "insight" && (
                    <div style={{ marginTop: 6 }}>
                      {p.findings.map((f: any, j: number) => (
                        <div key={j} style={{ marginBottom: 6 }}>
                          <span className="badge amber" style={{ marginRight: 6 }}>{f.hypothesis}</span>
                          <span className="muted" style={{ marginRight: 6 }}>[{f.axis}]</span>
                          {f.finding}
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

          {/* messages between agents (§4 audit log — the actual "behavior") */}
          {trace.communications?.length > 0 && (
            <div style={{ marginTop: 20, borderTop: "1px solid var(--border)", paddingTop: 12 }}>
              <h2>{c.messagesTitle}</h2>
              <table>
                <thead>
                  <tr><th>{t.common.time}</th><th>{t.common.senderReceiver}</th><th>intent</th><th>schema</th><th>conf.</th><th>HITL</th></tr>
                </thead>
                <tbody>
                  {trace.communications.map((m: any) => (
                    <tr key={m.message_id}>
                      <td className="muted">{m.timestamp?.slice(11, 19)}</td>
                      <td><span className="badge" style={{ background: "rgba(88,166,255,.15)", color: "var(--accent)" }}>{m.sender} → {m.receiver}</span></td>
                      <td>{m.intent}</td>
                      <td><code>{m.schema}</code></td>
                      <td className="muted">{m.confidence}</td>
                      <td>{m.human_gate_required ? <span className="badge red">{t.common.approvalNeeded}</span> : "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <div className="muted" style={{ marginTop: 6, fontSize: 12 }}>
                {t.common.auditFooter} <code>GET /messages</code>
              </div>
            </div>
          )}
        </div>
      )}
    </main>
  );
}
