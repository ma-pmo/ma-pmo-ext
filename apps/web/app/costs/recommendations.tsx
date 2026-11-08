"use client";
// Model recommendations: replay a step on the fast model, compare cost and quality with 95%
// intervals, and let an approver turn a recommended change into a draft. Nothing changes by itself.
import { Fragment, useEffect, useState } from "react";
import { api, problemsOf } from "../lib/api";
import { useI18n } from "../lib/i18n";
import { Card } from "../components/shell";

type Stat = { baseline: number; candidate: number; delta: number; ci95: [number, number]; n: [number, number] } | null;
type Rec = {
  id: number; workflow_id: string; step_id: string; verdict: string; status: string;
  draft_version: number | null; decided_by: string | null; created_at: string;
  report: {
    models: { baseline: string; candidate: string }; repeat: number; cost: Stat;
    quality: Record<string, Stat>; reasons: Reason[]; saving_pct: number | null; stopped_by_budget: boolean;
  };
};
type Flow = { id: string; title: string };
type Reason = { code: string; metric?: string; tolerance?: number };

const VERDICT_BADGE: Record<string, string> = { recommended: "green", not_recommended: "red", inconclusive: "amber" };
const fmt = (v: number, money: boolean) => (money ? `$${v.toFixed(4)}` : `${(v * 100).toFixed(0)}%`);
const signed = (v: number, money: boolean) => (v >= 0 ? "+" : "−") + fmt(Math.abs(v), money);

export function Recommendations() {
  const { lang, t } = useI18n();
  const c = t.cost;
  const [recs, setRecs] = useState<Rec[]>([]);
  const [flows, setFlows] = useState<Flow[]>([]);
  const [flow, setFlow] = useState("");
  const [steps, setSteps] = useState<{ id: string; agent: string; agent_name: string; model_tier: string }[]>([]);
  const [step, setStep] = useState("");
  const [repeat, setRepeat] = useState(3);
  const [busy, setBusy] = useState("");
  const [note, setNote] = useState<{ text: string; bad?: boolean } | null>(null);

  const load = () => api.recommendations().then(setRecs).catch(() => {});
  useEffect(() => {
    load();
    api.workflows().then((r) => { setFlows(r.workflows); setFlow((f) => f || r.workflows[0]?.id || ""); }).catch(() => {});
  }, [lang]);
  useEffect(() => {
    if (!flow) return;
    api.workflow(flow).then((d) => {
      const open = d.steps.filter((s: any) => s.model_tier !== "fast");
      setSteps(open);
      setStep(open[0]?.id ?? "");
    }).catch(() => setSteps([]));
  }, [flow, lang]);

  const run = async () => {
    setBusy("replay"); setNote(null);
    try { await api.replay(flow, step, repeat); await load(); }
    catch (e) { setNote({ text: problemsOf(e).join(" · "), bad: true }); }
    finally { setBusy(""); }
  };
  const decide = async (r: Rec, action: "approve" | "reject") => {
    setBusy(`${action}-${r.id}`); setNote(null);
    try {
      const done = await api.decide(r.id, action);
      if (done.draft_version) setNote({ text: c.draftMade(done.draft_version) });
      await load();
    } catch (e) { setNote({ text: problemsOf(e).join(" · "), bad: true }); }
    finally { setBusy(""); }
  };

  return (
    <Card title={c.recs} desc={c.recsDesc}>
      <div className="row budget-form" style={{ alignItems: "end" }}>
        <label><span>{c.workflow}</span>
          <select className="input" value={flow} onChange={(e) => setFlow(e.target.value)} style={{ width: 220 }}>
            {flows.map((f) => <option key={f.id} value={f.id}>{f.title}</option>)}
          </select>
        </label>
        <label><span>{c.step}</span>
          <select className="input" value={step} onChange={(e) => setStep(e.target.value)}>
            {steps.map((s) => <option key={s.id} value={s.id}>{s.id === s.agent ? s.id : `${s.id} (${s.agent})`} · {s.agent_name}</option>)}
          </select>
        </label>
        <label><span>{c.repeat}</span>
          <input className="input" type="number" min={2} max={50} value={repeat}
            onChange={(e) => setRepeat(Number(e.target.value))} style={{ width: 90 }} />
        </label>
        <button onClick={run} disabled={!step || busy !== ""}>{busy === "replay" ? c.replaying : c.replay}</button>
      </div>
      <p className="muted" style={{ margin: "6px 0 12px" }}>{c.recsCost}</p>
      {note && <p role="status"><span className={`badge ${note.bad ? "red" : "green"}`} style={{ whiteSpace: "normal" }}>{note.text}</span></p>}
      {recs.length === 0 ? <p className="muted">{c.noRecs}</p> : recs.map((r) => {
        const rows: [string, Stat, boolean][] = [["cost", r.report.cost, true],
          ...Object.entries(r.report.quality).map(([k, v]) => [k, v, false] as [string, Stat, boolean])];
        return (
          <div key={r.id} className="rec">
            <div className="row" style={{ justifyContent: "space-between" }}>
              <div className="row">
                <b>#{r.id} {r.workflow_id} / {r.step_id}</b>
                <span className={`badge ${VERDICT_BADGE[r.verdict] ?? ""}`}>{c.verdict[r.verdict] ?? r.verdict}</span>
                {r.report.saving_pct != null && r.report.saving_pct > 0 && <span className="badge accent">{c.cheaper(r.report.saving_pct)}</span>}
                <span className="muted">{c.status[r.status] ?? r.status}{r.decided_by ? ` · ${r.decided_by}` : ""}</span>
              </div>
              {r.status === "proposed" && (
                <div className="row">
                  {r.verdict === "recommended" && (
                    <button className="sm" onClick={() => decide(r, "approve")} disabled={busy !== ""}>{c.approve}</button>
                  )}
                  <button className="ghost sm" onClick={() => decide(r, "reject")} disabled={busy !== ""}>{c.reject}</button>
                </div>
              )}
            </div>
            <p className="muted" style={{ margin: "4px 0 8px" }}>
              <code>{r.report.models.baseline}</code> → <code>{r.report.models.candidate}</code> · {r.report.repeat} × 2
              {r.draft_version ? <> · <a href={`/workflows?id=${encodeURIComponent(r.workflow_id)}`}>{c.draftMade(r.draft_version)}</a></> : null}
            </p>
            <div className="table-wrap">
              <table className="cost-table">
                <thead><tr><th /><th>{c.baseline}</th><th>{c.candidate}</th><th>{c.delta}</th><th>{c.ci}</th></tr></thead>
                <tbody>
                  {rows.map(([k, s, money]) => (
                    <Fragment key={k}>
                      <tr>
                        <td>{c.metric[k] ?? k}</td>
                        {s ? (
                          <>
                            <td>{fmt(s.baseline, money)}</td><td>{fmt(s.candidate, money)}</td>
                            <td>{signed(s.delta, money)}</td>
                            <td>[{signed(s.ci95[0], money)}, {signed(s.ci95[1], money)}]</td>
                          </>
                        ) : <td colSpan={4} className="muted">–</td>}
                      </tr>
                    </Fragment>
                  ))}
                </tbody>
              </table>
            </div>
            <ul className="rec-reasons">
              {r.report.reasons.map((x, i) => (
                <li key={i}>{c.reason(x.code, c.metric[x.metric ?? ""] ?? x.metric ?? "", Math.round((x.tolerance ?? 0) * 100))}</li>
              ))}
              {r.report.stopped_by_budget && <li>{c.stoppedByBudget}</li>}
            </ul>
          </div>
        );
      })}
    </Card>
  );
}
