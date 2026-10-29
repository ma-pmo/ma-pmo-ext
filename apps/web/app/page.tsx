"use client";
import { useEffect, useState } from "react";
import { api } from "./lib/api";
import { useI18n } from "./lib/i18n";
import { BarRow, Gauge, StackBar, Tip } from "./components/charts";

const PORTFOLIO = "PORTFOLIO#2026-Q1";
const GATES = ["G1-initiation", "G2-planning", "G3-execution", "G4-closure"];
const STATUS_COLOR: Record<string, string> = { green: "var(--green)", amber: "var(--amber)", red: "var(--red)" };
const SELECT_STYLE = { flex: 1, background: "#0b0e14", color: "var(--text)", border: "1px solid var(--border)", borderRadius: 6, padding: "7px 10px" };

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
    <main className="grid" style={{ gap: 24 }}>
      <h1>{d.title(portfolio?.name ?? PORTFOLIO)}</h1>
      {err && <div className="card" style={{ color: "var(--red)" }}>{t.common.apiError}: {err} — <span className="muted">{t.common.checkApi}</span></div>}

      {/* legend */}
      <div className="card">
        <h2>{d.legendTitle}</h2>
        <div className="legend" style={{ marginBottom: 8 }}>
          <span className="item"><span className="dot green" />{d.legend.green}</span>
          <span className="item"><span className="dot amber" />{d.legend.amber}</span>
          <span className="item"><span className="dot red" />{d.legend.red}</span>
          <span className="item"><span className="dot accent" />{d.legend.agent}</span>
          <span className="item"><span className="dot purple" />{d.legend.hitl}</span>
        </div>
        <div className="muted" style={{ fontSize: 12, lineHeight: 1.7 }}>{d.metricGuide}</div>
      </div>

      {/* orchestration */}
      <div className="card">
        <h2>{d.orchestrateTitle}</h2>
        <div className="section-desc">{d.orchestrateDesc}</div>
        <div style={{ display: "flex", gap: 8 }}>
          <select value={goalIdx} onChange={(e) => setGoalIdx(Number(e.target.value))} style={SELECT_STYLE}>
            {d.goals.map((g, i) => <option key={i} value={i}>{g}</option>)}
          </select>
          <button onClick={runOrchestrate} disabled={running}>{running ? t.common.running : t.common.run}</button>
        </div>
        {result && (
          <div style={{ marginTop: 12 }}>
            {result.routing && (
              <div style={{ marginBottom: 6 }}>
                <span className="muted" style={{ marginRight: 8 }}>{d.routing(result.routing.mode)}</span>
                {(result.routing.delegations || []).map((del: any, i: number) => (
                  <span key={i} className="badge" style={{ background: "rgba(88,166,255,.15)", color: "var(--accent)", marginRight: 4 }}>{del.agent}</span>
                ))}
              </div>
            )}
            {result?.synthesis?.summary && <p style={{ marginTop: 6, fontSize: 14 }}>{result.synthesis.summary}</p>}
          </div>
        )}
      </div>

      {/* insights */}
      <div className="card">
        <h2>{d.insightsTitle}</h2>
        {insights.map((it, i) => <div key={i} className={`insight ${it.kind}`}>{it.text}</div>)}
      </div>

      {/* five-axis KPIs */}
      <div>
        <h2>{d.kpiTitle}</h2>
        <div className="grid cols-3">
          <div className="card"><div className="muted"><Tip text={d.kpi.rctTip}>{d.kpi.rct}</Tip></div>
            <div className="kpi-value">{byMetric("report_cycle_time_sec")?.avg?.toFixed(1) ?? "–"}s</div><div className="muted">n={byMetric("report_cycle_time_sec")?.count ?? 0}</div></div>
          <div className="card"><div className="muted"><Tip text={d.kpi.tokensTip}>{d.kpi.tokens}</Tip></div>
            <div className="kpi-value">{byMetric("llm_tokens_total")?.sum ?? "–"}</div><div className="muted">{d.kpi.calls} n={byMetric("llm_tokens_total")?.count ?? 0}</div></div>
          <div className="card"><div className="muted"><Tip text={d.kpi.rltTip}>{d.kpi.rlt}</Tip></div>
            <div className="kpi-value">{byMetric("risk_lead_time_days")?.avg?.toFixed(1) ?? "–"}{d.kpi.days}</div><div className="muted">{d.kpi.detected} n={byMetric("risk_detected")?.count ?? 0}</div></div>
          <div className="card"><div className="muted"><Tip text={d.kpi.utilTip}>{d.kpi.util}</Tip></div>
            <div className="kpi-value">{byMetric("utilization_pct")?.avg?.toFixed(0) ?? "–"}%</div><div className="muted">{d.kpi.idle} {byMetric("idle_pct")?.avg?.toFixed(0) ?? "–"}%</div></div>
          <div className="card"><div className="muted"><Tip text={d.kpi.spiTip}>{d.kpi.spi}</Tip></div>
            <div className="kpi-value">{byMetric("spi")?.avg?.toFixed(2) ?? "–"}</div><div className="muted">{d.kpi.slippage} {byMetric("projected_slippage_days")?.avg?.toFixed(0) ?? "–"}{d.kpi.days}</div></div>
          <div className="card"><div className="muted"><Tip text={d.kpi.gateTip}>{d.kpi.gate}</Tip></div>
            <div className="kpi-value">{byMetric("gate_review")?.avg?.toFixed(2) ?? "–"}</div><div className="muted">{d.kpi.reviews} n={byMetric("gate_review")?.count ?? 0}</div></div>
        </div>
      </div>

      {/* charts */}
      <div className="grid cols-2">
        <div className="card">
          <h2>{d.progressTitle}</h2>
          {projects.map((p: any) => (
            <BarRow key={p.project_id} label={`${p.project_id}`} value={p.percent_complete}
              color={STATUS_COLOR[p.status] || "var(--accent)"} suffix="%" />
          ))}
          <div className="legend" style={{ marginTop: 8 }}>{d.progressLegend}</div>
        </div>
        <div className="card">
          <h2>{d.utilTitle}</h2>
          <div style={{ display: "flex", justifyContent: "center", padding: "8px 0" }}>
            <Gauge value={Math.round(util ?? 0)} target={80} label={d.avgUtil} targetLabel={d.target} />
          </div>
        </div>
        <div className="card">
          <h2>{d.riskDistTitle}</h2>
          <StackBar segments={[
            { label: "high+", value: latestRisks.filter((r) => r.severity === "high" || r.severity === "critical").length, color: "var(--red)" },
            { label: "medium", value: latestRisks.filter((r) => r.severity === "medium").length, color: "var(--amber)" },
            { label: "low", value: latestRisks.filter((r) => r.severity === "low").length, color: "var(--green)" },
          ]} />
          <div className="muted" style={{ fontSize: 12, marginTop: 8 }}>{d.riskDistNote(latestRisks.length, risks.length)}</div>
        </div>
        <div className="card">
          <h2>{d.statusDistTitle}</h2>
          <StackBar segments={[
            { label: "red", value: reds.length, color: "var(--red)" },
            { label: "amber", value: projects.filter((p: any) => p.status === "amber").length, color: "var(--amber)" },
            { label: "green", value: projects.filter((p: any) => p.status === "green").length, color: "var(--green)" },
          ]} />
        </div>
      </div>

      {/* A2/A3 */}
      <div className="card">
        <h2>{d.planTitle}</h2>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <button onClick={runPlan}>{d.runPlan}</button>
          <button onClick={runAllocate}>{d.runAllocate}</button>
        </div>
        {allocations.length > 0 && (
          <div className="scroll-y" style={{ marginTop: 12 }}>
            <table>
              <thead><tr><th>{t.common.project}</th><th>{d.resource}</th><th>{d.week}</th><th>{d.hours}</th></tr></thead>
              <tbody>
                {allocations.map((a, i) => (
                  <tr key={i}><td>{a.project_id}</td><td>{a.resource_id}</td><td>{a.week}</td><td>{a.hours}h</td></tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {allocations.length > 0 && <div className="muted" style={{ fontSize: 12, marginTop: 6 }}>{d.allocTotal(allocations.length)}</div>}
      </div>

      {/* A6 / A7 */}
      <div className="grid cols-2">
        <div className="card">
          <h2>{d.gateTitle}</h2>
          <div style={{ display: "flex", gap: 8 }}>
            <select value={gate} onChange={(e) => setGate(e.target.value)} style={SELECT_STYLE}>
              {GATES.map((g) => <option key={g} value={g}>{d.gateLabels[g] ?? g}</option>)}
            </select>
            <button onClick={runGateReview}>{d.review}</button>
          </div>
          <div className="legend" style={{ margin: "8px 0" }}>
            <span className="item"><span className="dot green" />pass</span>
            <span className="item"><span className="dot amber" />conditional</span>
            <span className="item"><span className="dot red" />fail</span>
          </div>
          {gates.length > 0 && (
            <div className="scroll-y">
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
          )}
        </div>
        <div className="card">
          <h2>{d.knowledgeTitle}</h2>
          <div style={{ display: "flex", gap: 8 }}>
            <select value={queryIdx} onChange={(e) => setQueryIdx(Number(e.target.value))} style={SELECT_STYLE}>
              {d.queries.map((q, i) => <option key={i} value={i}>{q}</option>)}
            </select>
            <button onClick={runKnowledge}>{d.search}</button>
          </div>
          <div className="scroll-y" style={{ marginTop: 8 }}>
            {citations.length === 0 && <div className="muted" style={{ fontSize: 13 }}>{d.knowledgeEmpty}</div>}
            {citations.map((c) => (
              <div key={c.source_id} style={{ marginTop: 8, borderTop: "1px solid var(--border)", paddingTop: 8 }}>
                <div><strong>{c.title}</strong> <span className="muted">[{c.source_id}] sim={c.similarity}</span></div>
                <div className="muted" style={{ fontSize: 13 }}>{c.excerpt}…</div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* risk register */}
      <div className="card">
        <h2>{d.riskRegisterTitle}</h2>
        <div className="legend" style={{ marginBottom: 8 }}>
          <span className="item"><span className="dot red" />high/critical</span>
          <span className="item"><span className="dot amber" />medium</span>
          <span className="item"><span className="dot green" />low</span>
        </div>
        {risks.length === 0 ? (
          <div className="muted">{d.riskEmpty}</div>
        ) : (
          <div className="scroll-y">
            <table>
              <thead><tr><th>{t.common.project}</th><th>{t.common.severity}</th><th>{d.signal}</th><th>{d.mitigation}</th><th>{d.detectedAt}</th></tr></thead>
              <tbody>
                {risks.map((r) => (
                  <tr key={r.id}><td>{r.project_id}</td>
                    <td><span className={`badge ${r.severity === "high" || r.severity === "critical" ? "red" : r.severity === "medium" ? "amber" : "green"}`}>{r.severity}</span></td>
                    <td>{r.signal}</td><td className="muted">{r.mitigation}</td><td className="muted">{r.detected_at?.slice(0, 10)}</td></tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* project status */}
      <div className="card">
        <h2>{d.projectsTitle}</h2>
        <div className="scroll-y">
          <table>
            <thead><tr><th>{t.common.project}</th><th>{d.skill}</th><th>{t.common.status}</th><th>{d.progress}</th><th>{d.deadline}</th></tr></thead>
            <tbody>
              {projects.map((p: any) => (
                <tr key={p.project_id}><td>{p.project_id}</td><td>{p.skill}</td>
                  <td><span className={`badge ${p.status}`}>{p.status}</span></td>
                  <td>{p.percent_complete}%</td><td>{p.deadline}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </main>
  );
}
