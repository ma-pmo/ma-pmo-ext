"use client";
import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { useI18n } from "../lib/i18n";
import type { Messages } from "../lib/messages";

const APPROVER = "demo-approver@example.com";

// readable summary of a payload, per schema
function summarize(payload: any, m: Messages["appr"]["sum"]): { title: string; lines: string[] } {
  const schema = payload?.schema ?? "?";
  const d = payload?.data ?? {};
  if (schema === "risk_alert.v1")
    return { title: m.risk(d.project_id), lines: [`${m.severity}: ${d.severity}`, `${m.signal}: ${d.signal}`, `${m.mitigation}: ${d.mitigation}`] };
  if (schema === "gate_review.v1")
    return { title: m.gate(d.project_id, d.gate), lines: [`${m.decision}: ${d.decision}`, `${m.conditions}: ${(d.conditions || []).join("; ") || "—"}`] };
  if (schema === "report.v1")
    return { title: m.report(d.scope), lines: [d.executive_summary || "", m.projects(d.project_status?.length ?? 0)] };
  if (schema === "allocation.v1")
    return { title: m.alloc, lines: [m.allocs(d.plan?.length ?? 0), m.util(d.utilization_pct), m.overloads((d.overload_alerts || []).length)] };
  return { title: schema, lines: [JSON.stringify(d).slice(0, 120)] };
}

export default function Approvals() {
  const { lang, t } = useI18n();
  const a = t.appr;
  const reason = (it: any) => (it.confidence < 0.6 ? a.lowConfidence(it.confidence) : a.highRisk);
  const [items, setItems] = useState<any[]>([]);
  const [messages, setMessages] = useState<any[]>([]);
  const [raw, setRaw] = useState<Record<number, boolean>>({});
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState<number | null>(null);

  async function load() {
    try {
      setItems(await api.approvals());
      setMessages(await api.messages(15));
    } catch (e: any) { setErr(String(e.message || e)); }
  }
  useEffect(() => { load(); }, [lang]);

  async function decide(id: number, decision: "approve" | "reject") {
    setBusy(id); setErr("");
    try { await api.resolveApproval(id, APPROVER, decision); await load(); }
    catch (e: any) { setErr(String(e.message || e)); }
    finally { setBusy(null); }
  }

  // pending count per schema
  const bySchema = items.reduce((acc: Record<string, number>, it) => {
    const s = it.payload?.schema ?? "?"; acc[s] = (acc[s] || 0) + 1; return acc;
  }, {});

  return (
    <main className="grid" style={{ gap: 16 }}>
      <h1>{a.title}</h1>

      {/* description + legend */}
      <div className="card">
        <div className="section-desc" style={{ marginTop: 0 }}>
          {a.desc1}<b>propose</b>{a.desc2}
        </div>
        <div style={{ display: "flex", gap: 16, flexWrap: "wrap", alignItems: "center" }}>
          <div><span className="kpi-value" style={{ fontSize: 22 }}>{items.length}</span> <span className="muted">{a.pending}</span></div>
          <div className="legend">
            {Object.entries(bySchema).map(([s, n]) => (
              <span key={s} className="item"><span className="dot purple" /><code>{s}</code> {n}</span>
            ))}
          </div>
        </div>
      </div>

      {err && <div className="card" style={{ color: "var(--red)" }}>{t.common.apiError}: {err}</div>}
      {items.length === 0 && (
        <div className="card muted">
          {a.empty1} <code>POST /demo/gated-message</code>
        </div>
      )}

      {items.length > 25 && (
        <div className="muted" style={{ fontSize: 13 }}>{a.showingLatest(items.length)}</div>
      )}

      {/* approval cards */}
      {items.slice(0, 25).map((it) => {
        const s = summarize(it.payload, a.sum);
        return (
          <div className="card" key={it.approval_id}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12 }}>
              <div>
                <div style={{ marginBottom: 4 }}>
                  <span className="badge" style={{ background: "rgba(88,166,255,.15)", color: "var(--accent)", marginRight: 6 }}>{it.sender}</span>
                  <span className="muted">→ A1 · {it.intent}</span>
                  <span className="badge purple" style={{ background: "rgba(163,113,247,.15)", color: "#a371f7", marginLeft: 6 }}>{a.awaiting}</span>
                </div>
                <strong>{s.title}</strong>
                <div className="muted" style={{ fontSize: 13, marginTop: 2 }}>{s.lines.filter(Boolean).join(" · ")}</div>
                <div className="muted" style={{ fontSize: 12, marginTop: 4 }}>
                  {a.reason}: {reason(it)} · {it.task_ref} · {it.requested_at?.slice(0, 19).replace("T", " ")}
                </div>
              </div>
              <div style={{ display: "flex", gap: 8, flexShrink: 0 }}>
                <button onClick={() => decide(it.approval_id, "approve")} disabled={busy === it.approval_id}>{a.approve}</button>
                <button className="ghost" onClick={() => decide(it.approval_id, "reject")} disabled={busy === it.approval_id}>{a.reject}</button>
              </div>
            </div>
            <button className="ghost" style={{ marginTop: 8, fontSize: 12, padding: "3px 8px" }}
              onClick={() => setRaw((r) => ({ ...r, [it.approval_id]: !r[it.approval_id] }))}>
              {raw[it.approval_id] ? a.hideRaw : a.showRaw}
            </button>
            {raw[it.approval_id] && (
              <pre className="muted scroll-y" style={{ marginTop: 8, fontSize: 12 }}>
                {JSON.stringify(it.payload, null, 2)}
              </pre>
            )}
          </div>
        );
      })}

      {/* audit log */}
      <div className="card">
        <h2>{a.recentTitle}</h2>
        <div className="section-desc" style={{ marginTop: 0 }}>
          {a.recentDesc} <code>GET /messages</code>
        </div>
        <div className="scroll-y">
          <table>
            <thead><tr><th>{t.common.time}</th><th>{t.common.senderReceiver}</th><th>intent</th><th>schema</th><th>conf.</th><th>HITL</th></tr></thead>
            <tbody>
              {messages.map((m) => (
                <tr key={m.message_id}>
                  <td className="muted">{m.timestamp?.slice(11, 19)}</td>
                  <td><span className="badge" style={{ background: "rgba(88,166,255,.15)", color: "var(--accent)" }}>{m.sender}→{m.receiver}</span></td>
                  <td>{m.intent}</td>
                  <td><code>{m.schema}</code></td>
                  <td className="muted">{m.confidence}</td>
                  <td>{m.human_gate_required ? <span className="badge red">{t.common.approvalNeeded}</span> : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </main>
  );
}
