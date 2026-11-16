"use client";
import { Fragment, useEffect, useState } from "react";
import { api, errorText } from "../lib/api";
import { useI18n } from "../lib/i18n";
import { clock, when } from "../lib/time";
import type { Messages } from "../lib/messages";
import { Card, PageHeader, Stat, ErrorCard } from "../components/shell";
import { Icon } from "../components/icons";
import { ReviewDetail } from "../components/review";

const APPROVER = "demo-approver@example.com";
const PAGE = 50;

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
      setErr("");
    } catch (e: any) { setErr(errorText(e)); }
  }
  useEffect(() => { load(); }, [lang]);

  async function decide(id: number, decision: "approve" | "reject") {
    setBusy(id); setErr("");
    try { await api.resolveApproval(id, APPROVER, decision); await load(); }
    catch (e: any) { setErr(errorText(e)); }
    finally { setBusy(null); }
  }

  // pending count per schema
  const bySchema = items.reduce((acc: Record<string, number>, it) => {
    const s = it.payload?.schema ?? "?"; acc[s] = (acc[s] || 0) + 1; return acc;
  }, {});
  const lowConf = items.filter((it) => it.confidence < 0.6).length;

  return (
    <div className="stack">
      <PageHeader
        title={a.title}
        desc={t.pages.approvals}
        actions={<button className="ghost" onClick={load}><Icon.refresh />{t.common2.refresh}</button>}
      />
      {err && <ErrorCard label={t.common.apiError}>{err}</ErrorCard>}

      <div className="grid cols-4">
        <Stat icon={<Icon.approvals />} label={a.awaiting} value={items.length} sub={a.pending} />
        <Stat icon={<Icon.alert />} label="risk_alert.v1" value={bySchema["risk_alert.v1"] ?? 0} />
        <Stat icon={<Icon.gate />} label="gate_review.v1" value={bySchema["gate_review.v1"] ?? 0} />
        <Stat icon={<Icon.trend />} label="confidence < 0.6" value={lowConf} />
      </div>

      <Card flush title={a.title} desc={<>{a.desc1}<b>propose</b>{a.desc2}</>}>
        {items.length === 0 ? (
          <div className="empty">{a.empty1} <code>POST /demo/gated-message</code></div>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr><th>#</th><th>{t.common.senderReceiver}</th><th>{t.evalp.claim}</th><th>{a.reason}</th><th className="num">conf.</th><th /></tr>
              </thead>
              <tbody>
                {items.slice(0, PAGE).map((it) => {
                  const s = summarize(it.payload, a.sum);
                  return (
                    <Fragment key={it.approval_id}>
                      <tr>
                        <td className="muted">{it.approval_id}</td>
                        <td><span className="badge accent">{it.sender} → A1</span><div className="muted" style={{ whiteSpace: "nowrap" }}>{when(it.requested_at, lang)}</div></td>
                        <td>
                          <b>{s.title}</b>
                          <div className="muted">{s.lines.filter(Boolean).join(" · ")}</div>
                          <button className="ghost sm" style={{ marginTop: 6 }}
                            onClick={() => setRaw((r) => ({ ...r, [it.approval_id]: !r[it.approval_id] }))}>
                            {raw[it.approval_id] ? a.hideRaw : a.showRaw}
                          </button>
                        </td>
                        <td>
                          {it.review
                            ? <span className="badge amber tip" data-tip={t.rv.pendingTip}>{t.rv.pending}</span>
                            : <span className={`badge ${it.confidence < 0.6 ? "amber" : "purple"}`}>{reason(it)}</span>}
                          <div className="muted">{it.task_ref}</div>
                        </td>
                        <td className="num">{it.confidence}</td>
                        <td>
                          <div className="row" style={{ flexWrap: "nowrap" }}>
                            <button className="sm" onClick={() => decide(it.approval_id, "approve")} disabled={busy === it.approval_id}>{a.approve}</button>
                            <button className="sm ghost" onClick={() => decide(it.approval_id, "reject")} disabled={busy === it.approval_id}>{a.reject}</button>
                          </div>
                        </td>
                      </tr>
                      {it.review && (
                        <tr className="rv-row"><td /><td colSpan={5}><ReviewDetail review={it.review} /></td></tr>
                      )}
                      {raw[it.approval_id] && (
                        <tr><td colSpan={6}><pre className="code">{JSON.stringify(it.payload, null, 2)}</pre></td></tr>
                      )}
                    </Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
        {items.length > PAGE && <div className="muted" style={{ padding: "8px 16px" }}>{a.showingLatest(items.length, PAGE)}</div>}
      </Card>

      <Card flush title={a.recentTitle} desc={<>{a.recentDesc} <code>GET /messages</code></>}>
        <div className="table-wrap scroll-y">
          <table>
            <thead><tr><th>{t.common.time}</th><th>{t.common.senderReceiver}</th><th>intent</th><th>schema</th><th className="num">conf.</th><th>HITL</th></tr></thead>
            <tbody>
              {messages.map((m) => (
                <tr key={m.message_id}>
                  <td className="muted" style={{ whiteSpace: "nowrap" }}>{clock(m.timestamp, lang)}</td>
                  <td><span className="badge accent">{m.sender}→{m.receiver}</span></td>
                  <td>{m.intent}</td>
                  <td><code>{m.schema}</code></td>
                  <td className="num muted">{m.confidence}</td>
                  <td>{m.human_gate_required ? <span className="badge red">{t.common.approvalNeeded}</span> : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}
