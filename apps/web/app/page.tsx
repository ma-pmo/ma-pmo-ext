"use client";
import { useEffect, useState } from "react";
import { api } from "./lib/api";
import { useI18n } from "./lib/i18n";
import { BarRow, Gauge, StackBar } from "./components/charts";
import { Card, PageHeader, Stat } from "./components/shell";
import { Icon } from "./components/icons";

const PORTFOLIO = "PORTFOLIO#2026-Q1";
const GATES = ["G1-initiation", "G2-planning", "G3-execution", "G4-closure"];
const STATUS_COLOR: Record<string, string> = { green: "var(--green)", amber: "var(--amber)", red: "var(--red)" };
const sevClass = (s: string) => (s === "high" || s === "critical" ? "red" : s === "medium" ? "amber" : "green");
const fmt = (v: number | undefined | null, digits = 1) => (v == null ? "–" : v.toFixed(digits));

export default function Dashboard() {
  const { lang, t } = useI18n();
  const d = t.dash;
  const [portfolio, setPortfolio] = useState<any>(null);
  const [kpi, setKpi] = useState<any>(null);
  const [risks, setRisks] = useState<any[]>([]);
  const [allocations, setAllocations] = useState<any[]>([]);
  const [gates, setGates] = useState<any[]>([]);
  const [gate, setGate] = useState("G2-planning");
  const [queryIdx, setQueryIdx] = useState(0);
  const [citations, setCitations] = useState<any[]>([]);
  const [goalIdx, setGoalIdx] = useState(0);
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [err, setErr] = useState<string>("");

  async function load() {
    try {
      setPortfolio(await api.portfolio(PORTFOLIO));
      setKpi(await api.kpi());
      setRisks(await api.risks());
      setAllocations(await api.allocations());
      setErr("");
    } catch (e: any) { setErr(String(e.message || e)); }
  }
  // reload when the language changes so server-generated text follows it
  useEffect(() => { load(); setCitations([]); setGates([]); setResult(null); }, [lang]);

  const guard = (fn: () => Promise<void>) => async () => {
    setErr("");
    try { await fn(); } catch (e: any) { setErr(String(e.message || e)); }
  };
  const runOrchestrate = guard(async () => {
    setRunning(true);
    try { setResult(await api.orchestrate(d.goals[goalIdx], PORTFOLIO)); await load(); }
    finally { setRunning(false); }
  });
  const runPlan = guard(async () => { await api.plan(); await load(); });
  const runAllocate = guard(async () => { await api.allocate(); await load(); });
  const runGateReview = guard(async () => { setGates((await api.gateReview(gate)).reviews || []); await load(); });
  const runKnowledge = guard(async () => { setCitations((await api.knowledgeSearch(d.queries[queryIdx])).citations || []); });

  const summary = kpi?.summary ?? [];
  const byMetric = (m: string) => summary.find((s: any) => s.metric === m);
  const projects = portfolio?.projects ?? [];

  // ── data-driven insights ──
  const util = byMetric("utilization_pct")?.avg;
  const worstSpi = projects.length
    ? [...projects].sort((a, b) => (a.percent_complete) - (b.percent_complete))[0] : null;
  const reds = projects.filter((p: any) => p.status === "red");
  const highRisks = risks.filter((r) => r.severity === "high" || r.severity === "critical");
  const highRiskProjects = [...new Set(highRisks.map((r) => r.project_id))];
  // latest risk per project (rows are sorted newest first) — for the distribution chart
  const latestRisks = Object.values(
    risks.reduce((acc: any, r) => { if (!acc[r.project_id]) acc[r.project_id] = r; return acc; }, {})
  ) as any[];
  const insights: { kind: string; text: string }[] = [];
  if (reds.length) insights.push({ kind: "warn", text: d.insightRed(reds.length, reds.map((p: any) => p.project_id).join(", ")) });
  if (highRiskProjects.length) insights.push({ kind: "warn", text: d.insightHighRisk(highRiskProjects.length, highRiskProjects.join(", "), highRisks.length) });
  if (util != null && util < 80) insights.push({ kind: "", text: d.insightUtil(Math.round(util), Math.round(100 - util)) });
  if (worstSpi) insights.push({ kind: "", text: d.insightWorst(worstSpi.project_id, worstSpi.percent_complete) });
  if (!insights.length) insights.push({ kind: "ok", text: d.insightOk });

  return (
    <div className="stack">
      <PageHeader
        title={portfolio?.name ?? PORTFOLIO}
        desc={t.pages.dashboard}
        actions={<button className="ghost" onClick={load}><Icon.refresh />{t.common2.refresh}</button>}
      />
      {err && <div className="card" style={{ color: "var(--red)" }}>{t.common.apiError}: {err} — <span className="muted">{t.common.checkApi}</span></div>}

      {/* five-axis KPIs */}
      <div className="grid cols-6">
        <Stat icon={<Icon.clock />} label={d.kpi.rct} tip={d.kpi.rctTip}
          value={`${fmt(byMetric("report_cycle_time_sec")?.avg)}s`} sub={`n=${byMetric("report_cycle_time_sec")?.count ?? 0}`} />
        <Stat icon={<Icon.users />} label={d.kpi.util} tip={d.kpi.utilTip}
          value={`${fmt(byMetric("utilization_pct")?.avg, 0)}%`} sub={`${d.kpi.idle} ${fmt(byMetric("idle_pct")?.avg, 0)}%`} />
        <Stat icon={<Icon.trend />} label={d.kpi.spi} tip={d.kpi.spiTip}
          value={fmt(byMetric("spi")?.avg, 2)} sub={`${d.kpi.slippage} ${fmt(byMetric("projected_slippage_days")?.avg, 0)}${d.kpi.days}`} />
        <Stat icon={<Icon.alert />} label={d.kpi.rlt} tip={d.kpi.rltTip}
          value={`${fmt(byMetric("risk_lead_time_days")?.avg)}${d.kpi.days}`} sub={`${d.kpi.detected} n=${byMetric("risk_detected")?.count ?? 0}`} />
        <Stat icon={<Icon.gate />} label={d.kpi.gate} tip={d.kpi.gateTip}
          value={fmt(byMetric("gate_review")?.avg, 2)} sub={`${d.kpi.reviews} n=${byMetric("gate_review")?.count ?? 0}`} />
        <Stat icon={<Icon.coins />} label={d.kpi.tokens} tip={d.kpi.tokensTip}
          value={byMetric("llm_tokens_total")?.sum ?? "–"} sub={`${d.kpi.calls} n=${byMetric("llm_tokens_total")?.count ?? 0}`} />
      </div>

      {/* orchestration + insights */}
      <div className="grid cols-3 top">
        <Card className="span-2" title={d.orchestrateTitle} desc={d.orchestrateDesc}>
          <div className="row">
            <select className="input" style={{ flex: 1 }} value={goalIdx} onChange={(e) => setGoalIdx(Number(e.target.value))}>
              {d.goals.map((g, i) => <option key={i} value={i}>{g}</option>)}
            </select>
            <button onClick={runOrchestrate} disabled={running}>{running ? t.common.running : t.common.run}</button>
          </div>
          {result && (
            <div style={{ marginTop: 12 }}>
              {result.routing && (
                <div className="row" style={{ marginBottom: 6 }}>
                  <span className="muted">{d.routing(result.routing.mode)}</span>
                  {(result.routing.delegations || []).map((del: any, i: number) => (
                    <span key={i} className="badge accent">{del.agent}</span>
                  ))}
                </div>
              )}
              {result?.synthesis?.summary && <p style={{ margin: "6px 0 0" }}>{result.synthesis.summary}</p>}
            </div>
          )}
          <details style={{ marginTop: 14 }}>
            <summary>{d.legendTitle}</summary>
            <div className="legend" style={{ margin: "8px 0" }}>
              <span className="item"><span className="dot green" />{d.legend.green}</span>
              <span className="item"><span className="dot amber" />{d.legend.amber}</span>
              <span className="item"><span className="dot red" />{d.legend.red}</span>
              <span className="item"><span className="dot accent" />{d.legend.agent}</span>
              <span className="item"><span className="dot purple" />{d.legend.hitl}</span>
            </div>
            <div className="muted">{d.metricGuide}</div>
          </details>
        </Card>
        <Card title={d.insightsTitle}>
          {insights.map((it, i) => <div key={i} className={`insight ${it.kind}`}>{it.text}</div>)}
        </Card>
      </div>

      {/* charts */}
      <div className="grid cols-4">
        <Card title={d.progressTitle}>
          {projects.map((p: any) => (
            <BarRow key={p.project_id} label={`${p.project_id}`} value={p.percent_complete}
              color={STATUS_COLOR[p.status] || "var(--accent)"} suffix="%" />
          ))}
          <div className="legend" style={{ marginTop: 8 }}>{d.progressLegend}</div>
        </Card>
        <Card title={d.utilTitle}>
          <div style={{ display: "flex", justifyContent: "center" }}>
            <Gauge value={Math.round(util ?? 0)} target={80} label={d.avgUtil} targetLabel={d.target} />
          </div>
        </Card>
        <Card title={d.riskDistTitle}>
          <StackBar segments={[
            { label: "high+", value: latestRisks.filter((r) => r.severity === "high" || r.severity === "critical").length, color: "var(--red)" },
            { label: "medium", value: latestRisks.filter((r) => r.severity === "medium").length, color: "var(--amber)" },
            { label: "low", value: latestRisks.filter((r) => r.severity === "low").length, color: "var(--green)" },
          ]} />
          <div className="muted" style={{ marginTop: 8 }}>{d.riskDistNote(latestRisks.length, risks.length)}</div>
        </Card>
        <Card title={d.statusDistTitle}>
          <StackBar segments={[
            { label: "red", value: reds.length, color: "var(--red)" },
            { label: "amber", value: projects.filter((p: any) => p.status === "amber").length, color: "var(--amber)" },
            { label: "green", value: projects.filter((p: any) => p.status === "green").length, color: "var(--green)" },
          ]} />
        </Card>
      </div>

      {/* projects + risk register */}
      <div className="grid cols-2">
        <Card flush title={d.projectsTitle}>
          <div className="table-wrap">
            <table>
              <thead><tr><th>{t.common.project}</th><th>{d.skill}</th><th>{t.common.status}</th><th className="num">{d.progress}</th><th>{d.deadline}</th></tr></thead>
              <tbody>
                {projects.map((p: any) => (
                  <tr key={p.project_id}><td><b>{p.project_id}</b></td><td>{p.skill}</td>
                    <td><span className={`badge ${p.status}`}>{p.status}</span></td>
                    <td className="num">{p.percent_complete}%</td><td>{p.deadline}</td></tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
        <Card flush title={d.riskRegisterTitle}>
          {risks.length === 0 ? <div className="empty">{d.riskEmpty}</div> : (
            <div className="table-wrap scroll-y">
              <table>
                <thead><tr><th>{t.common.project}</th><th>{t.common.severity}</th><th>{d.signal}</th><th>{d.detectedAt}</th></tr></thead>
                <tbody>
                  {risks.map((r) => (
                    <tr key={r.id} title={r.mitigation}><td><b>{r.project_id}</b></td>
                      <td><span className={`badge ${sevClass(r.severity)}`}>{r.severity}</span></td>
                      <td>{r.signal}</td><td className="muted">{r.detected_at?.slice(0, 10)}</td></tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      </div>

      {/* A2/A3 · A6 · A7 */}
      <div className="grid cols-3">
        <Card flush title={d.planTitle} actions={
          <div className="row"><button className="sm" onClick={runPlan}>{d.runPlan}</button>
            <button className="sm ghost" onClick={runAllocate}>{d.runAllocate}</button></div>}>
          {allocations.length > 0 ? (
            <div className="table-wrap scroll-y">
              <table>
                <thead><tr><th>{t.common.project}</th><th>{d.resource}</th><th>{d.week}</th><th className="num">{d.hours}</th></tr></thead>
                <tbody>
                  {allocations.map((a, i) => (
                    <tr key={i}><td>{a.project_id}</td><td>{a.resource_id}</td><td>{a.week}</td><td className="num">{a.hours}h</td></tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : <div className="empty">–</div>}
        </Card>
        <Card flush title={d.gateTitle} actions={
          <div className="row">
            <select className="input" value={gate} onChange={(e) => setGate(e.target.value)}>
              {GATES.map((g) => <option key={g} value={g}>{d.gateLabels[g] ?? g}</option>)}
            </select>
            <button className="sm" onClick={runGateReview}>{d.review}</button>
          </div>}>
          {gates.length > 0 ? (
            <div className="table-wrap scroll-y">
              <table>
                <thead><tr><th>{t.common.project}</th><th>{d.decision}</th><th>{d.conditions}</th></tr></thead>
                <tbody>
                  {gates.filter(Boolean).map((g) => (
                    <tr key={g.project_id}><td>{g.project_id}</td>
                      <td><span className={`badge ${g.decision === "pass" ? "green" : g.decision === "conditional" ? "amber" : "red"}`}>{g.decision}</span></td>
                      <td className="muted">{(g.conditions || []).join("; ") || "–"}</td></tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : <div className="empty">pass · conditional · fail</div>}
        </Card>
        <Card title={d.knowledgeTitle}>
          <div className="row">
            <select className="input" style={{ flex: 1 }} value={queryIdx} onChange={(e) => setQueryIdx(Number(e.target.value))}>
              {d.queries.map((q, i) => <option key={i} value={i}>{q}</option>)}
            </select>
            <button className="sm" onClick={runKnowledge}>{d.search}</button>
          </div>
          <div className="scroll-y" style={{ marginTop: 8 }}>
            {citations.length === 0 && <div className="muted" style={{ paddingTop: 8 }}>{d.knowledgeEmpty}</div>}
            {citations.map((c) => (
              <div key={c.source_id} style={{ marginTop: 10, paddingTop: 10, borderTop: "1px solid var(--border)" }}>
                <div><b>{c.title}</b> <span className="badge">{c.source_id}</span></div>
                <div className="muted">{c.excerpt}…</div>
              </div>
            ))}
          </div>
        </Card>
      </div>
    </div>
  );
}
