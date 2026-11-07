"use client";
// Read-only workflow view: the steps of a WorkflowSpec as a graph (columns = stages that can run
// in parallel) with the same steps as a table. Layout is computed here; no graph library needed.
// Picking a run draws the workflow that run saved, with where each step stands, and keeps it
// current while the run is going.
import { useEffect, useRef, useState } from "react";
import { api } from "../lib/api";
import { useI18n } from "../lib/i18n";
import { Card, PageHeader } from "../components/shell";

type StepRun = {
  status: string; attempts?: number; error?: string | null; pending_approvals: number;
  started_at?: string | null; finished_at?: string | null;
};
type Step = {
  id: string; agent: string; agent_name: string; params: Record<string, unknown>;
  needs: string[]; required: boolean; level: number; run?: StepRun;
};
type RunSummary = { run_id: string; kind: string; workflow: string; scope: string; status: string; started_at: string };
type Workflow = {
  id: string; version: number; title: string; category: string; description: string;
  hypotheses: string[]; source: "builtin" | "custom"; agents: string[]; steps?: Step[];
  run?: RunSummary; same_as_current?: boolean;
};

const POLL_MS = 2000;
// In a paused run, a step that queued an approval is what the run waits on. A run that did not
// pause has finished that step; its approvals are only waiting in the queue.
const stepState = (r: StepRun | undefined, run: string | undefined) =>
  (!r ? "" : r.pending_approvals > 0 && run === "waiting_approval" ? "waiting_approval" : r.status);
const when = (iso?: string) => (iso ? new Date(iso).toLocaleString() : "");

const W = 188, H = 60, GAP_X = 64, GAP_Y = 16, PAD = 10;

function layout(steps: Step[]) {
  const rows: Record<number, number> = {};
  const pos: Record<string, { x: number; y: number }> = {};
  for (const s of steps) {
    const row = (rows[s.level] = (rows[s.level] ?? -1) + 1);
    pos[s.id] = { x: PAD + s.level * (W + GAP_X), y: PAD + 22 + row * (H + GAP_Y) };
  }
  const levels = Math.max(0, ...steps.map((s) => s.level)) + 1;
  const height = PAD * 2 + 22 + Math.max(...Object.values(rows), 0) * (H + GAP_Y) + H;
  return { pos, levels, width: PAD * 2 + levels * W + (levels - 1) * GAP_X, height };
}

const params = (p: Record<string, unknown>) =>
  Object.entries(p).map(([k, v]) => `${k}=${typeof v === "string" ? v : JSON.stringify(v)}`).join(", ");

// the table shows the full text; a node keeps one line
const clip = (text: string, n: number) => (text.length > n ? `${text.slice(0, n - 1)}…` : text);

function Graph({ steps, active, setActive, runStatus }: {
  steps: Step[]; active: string; setActive: (id: string) => void; runStatus?: string;
}) {
  const { t } = useI18n();
  const w = t.wf;
  const { pos, levels, width, height } = layout(steps);
  const lit = (from: string, to: string) => active === from || active === to;
  return (
    <div className="wf-graph">
      <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} role="list" aria-label={w.graph}>
        <defs>
          <marker id="wf-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto">
            <path d="M0 0L10 5L0 10z" className="wf-arrow" />
          </marker>
          <marker id="wf-arrow-on" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto">
            <path d="M0 0L10 5L0 10z" className="wf-arrow on" />
          </marker>
        </defs>
        {Array.from({ length: levels }, (_, i) => (
          <text key={i} x={PAD + i * (W + GAP_X)} y={PAD + 10} className="wf-stage">{w.level(i)}</text>
        ))}
        {steps.flatMap((s) => s.needs.map((n) => {
          const a = pos[n], b = pos[s.id];
          const x1 = a.x + W, y1 = a.y + H / 2, x2 = b.x - 2, y2 = b.y + H / 2, mid = (x1 + x2) / 2;
          const on = lit(n, s.id);
          return (
            <path key={`${n}-${s.id}`} d={`M${x1} ${y1}C${mid} ${y1} ${mid} ${y2} ${x2} ${y2}`}
              className={`wf-edge ${on ? "on" : ""}`} markerEnd={`url(#wf-arrow${on ? "-on" : ""})`} />
          );
        }))}
        {steps.map((s) => {
          const { x, y } = pos[s.id];
          return (
            <g key={s.id} role="listitem" tabIndex={0} transform={`translate(${x} ${y})`}
              className={`wf-node ${s.required ? "required" : ""} ${active === s.id ? "on" : ""} ${s.run ? `st-${stepState(s.run, runStatus)}` : ""}`}
              aria-label={`${w.nodeLabel(s.id, s.agent_name, s.needs, s.required)}${s.run ? `, ${w.status[stepState(s.run, runStatus)] ?? stepState(s.run, runStatus)}` : ""}`}
              onFocus={() => setActive(s.id)} onMouseEnter={() => setActive(s.id)} onClick={() => setActive(s.id)}>
              <rect width={W} height={H} rx="10" />
              <text x="12" y="23" className="wf-title">{s.agent} · {s.agent_name}</text>
              <text x="12" y="44" className="wf-sub">
                {clip(`${s.id}${Object.keys(s.params).length ? ` · ${params(s.params)}` : ""}`, 28)}
              </text>
              {s.run
                ? <text x={W - 10} y="23" textAnchor="end" className="wf-state">{w.status[stepState(s.run, runStatus)] ?? stepState(s.run, runStatus)}</text>
                : s.required && <text x={W - 10} y="23" textAnchor="end" className="wf-lock">{w.required}</text>}
            </g>
          );
        })}
      </svg>
    </div>
  );
}

export default function Workflows() {
  const { lang, t } = useI18n();
  const w = t.wf;
  const [list, setList] = useState<Workflow[]>([]);
  const [problems, setProblems] = useState<string[]>([]);
  const [selected, setSelected] = useState("");
  const [detail, setDetail] = useState<Workflow | null>(null);
  const [active, setActive] = useState("");
  const [err, setErr] = useState("");
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [runId, setRunId] = useState("");
  const [overlay, setOverlay] = useState<Workflow | null>(null);
  // what the URL asked for, read once before this page rewrites the URL
  const asked = useRef<{ id: string | null; run: string | null } | null>(null);
  if (asked.current === null && typeof window !== "undefined") {
    const q = new URLSearchParams(window.location.search);
    asked.current = { id: q.get("id"), run: q.get("run") };
  }

  useEffect(() => {
    api.workflows().then((r) => {
      setList(r.workflows);
      setProblems(r.problems);
      const wanted = asked.current?.id;
      setSelected((cur) => cur || (r.workflows.some((x: Workflow) => x.id === wanted) ? wanted! : r.workflows[0]?.id || ""));
    }).catch((e) => setErr(String(e.message || e)));
  }, [lang]);

  useEffect(() => {
    if (!selected) return;
    setActive("");
    api.workflow(selected).then(setDetail).catch((e) => setErr(String(e.message || e)));
    api.runs({ workflow: selected, limit: 20 }).then((r: RunSummary[]) => {
      setRuns(r);
      const wanted = asked.current?.run;
      if (asked.current) asked.current.run = null;
      setRunId(wanted && r.some((x) => x.run_id === wanted) ? wanted : "");
    }).catch(() => setRuns([]));
    // bring the chosen item into the list's own view without scrolling the page
    const item = document.querySelector<HTMLElement>(".wf-list button.on");
    const box = item?.parentElement;
    if (item && box && (item.offsetTop < box.scrollTop || item.offsetTop > box.scrollTop + box.clientHeight - item.offsetHeight)) {
      box.scrollTop = item.offsetTop - box.clientHeight / 2;
    }
  }, [selected, lang]);

  useEffect(() => {
    if (!selected) return;
    window.history.replaceState(null, "",
      `?id=${encodeURIComponent(selected)}${runId ? `&run=${encodeURIComponent(runId)}` : ""}`);
  }, [selected, runId]);

  useEffect(() => {
    setOverlay(null);
    if (!runId) return;
    let alive = true;
    let timer: ReturnType<typeof setTimeout>;
    const load = async () => {
      try {
        const o: Workflow = await api.runWorkflow(runId);
        if (!alive) return;
        setOverlay(o);
        const now = o.run;
        if (now) setRuns((rs) => rs.map((r) => (r.run_id === now.run_id ? { ...r, status: now.status } : r)));
        if (o.run?.status === "running") timer = setTimeout(load, POLL_MS);
      } catch (e: any) { if (alive) setErr(String(e.message || e)); }
    };
    load();
    return () => { alive = false; clearTimeout(timer); };
  }, [runId, lang]);

  const shown = overlay ?? detail;
  const runStatus = overlay?.run?.status;

  return (
    <div className="stack">
      <PageHeader title={t.nav.workflows} desc={t.pages.workflows} />
      {err && <div className="card" style={{ color: "var(--red)" }}>{t.common.error}: {err}</div>}
      {problems.length > 0 && (
        <Card title={w.problems}>
          <ul className="muted" style={{ margin: 0 }}>{problems.map((p) => <li key={p}><code>{p}</code></li>)}</ul>
        </Card>
      )}
      <div className="wf-layout">
        {/* phones: a menu, so the graph is not pushed below twenty items */}
        <label className="wf-pick">
          <span className="muted">{w.list}</span>
          <select className="input" value={selected} onChange={(e) => setSelected(e.target.value)}>
            {list.map((x) => <option key={x.id} value={x.id}>{x.title}</option>)}
          </select>
        </label>
        <Card title={w.list} flush className="wf-side">
          <div className="wf-list" role="listbox" aria-label={w.list}>
            {list.map((x) => (
              <button key={x.id} role="option" aria-selected={selected === x.id}
                className={selected === x.id ? "on" : ""} onClick={() => setSelected(x.id)}>
                <b>{x.title}</b>
                <span className="muted">{x.category} · {x.source === "builtin" ? w.builtin : w.custom}</span>
              </button>
            ))}
          </div>
        </Card>

        {shown?.steps && (
          <div className="stack" style={{ minWidth: 0 }}>
            <Card title={shown.title}
              desc={`${shown.description} · ${w.version(shown.version)} · ${shown.hypotheses.join(", ")}`}
              actions={runs.length > 0 && (
                <label className="row" style={{ gap: 6 }}>
                  <span className="muted">{w.run}</span>
                  <select className="input" value={runId} onChange={(e) => setRunId(e.target.value)}>
                    <option value="">{w.noRun}</option>
                    {runs.map((r) => (
                      <option key={r.run_id} value={r.run_id}>
                        {when(r.started_at)} · {w.status[r.status] ?? r.status}
                      </option>
                    ))}
                  </select>
                </label>
              )}>
              {overlay?.run && (
                <div className="wf-runbar" aria-live="polite">
                  <span className={`badge ${w.badge[overlay.run.status] ?? ""}`}>{w.status[overlay.run.status] ?? overlay.run.status}</span>
                  <span className="muted">{overlay.run.scope} · {when(overlay.run.started_at)} · <code>{overlay.run.run_id}</code></span>
                  {overlay.run.status === "waiting_approval" && <a href="/approvals">{w.toApprovals}</a>}
                  {overlay.same_as_current === false && <span className="badge amber">{w.olderVersion}</span>}
                </div>
              )}
              <p className="muted" style={{ margin: "0 0 10px" }}>{w.graphHint}</p>
              <Graph steps={shown.steps} active={active} setActive={setActive} runStatus={runStatus} />
              {overlay && (
                <div className="wf-legend">
                  {["succeeded", "running", "waiting_approval", "failed", "not_started"].map((k) => (
                    <span key={k} className={`st-${k}`}><i />{w.status[k]}</span>
                  ))}
                </div>
              )}
            </Card>
            <Card title={w.table} flush>
              <div className="table-wrap">
                <table className="wf-table">
                  <thead>
                    <tr><th>{w.step}</th><th>{w.agent}</th><th>{w.waitsFor}</th><th>{w.params}</th><th>{w.required}</th>{overlay && <th>{w.state}</th>}</tr>
                  </thead>
                  <tbody>
                    {shown.steps.map((s) => (
                      <tr key={s.id} className={active === s.id ? "wf-row-on" : ""}>
                        <td><code>{s.id}</code></td>
                        <td>{s.agent} · {s.agent_name}</td>
                        <td>{s.needs.length ? s.needs.join(", ") : <span className="muted">{w.start}</span>}</td>
                        <td>{Object.keys(s.params).length ? <code>{params(s.params)}</code> : <span className="muted">–</span>}</td>
                        <td>{s.required
                          ? <span className="badge amber tip" data-tip={w.requiredTip}>{w.required}</span>
                          : <span className="muted">–</span>}</td>
                        {overlay && <td>
                          {w.status[stepState(s.run, runStatus)] ?? stepState(s.run, runStatus)}
                          {s.run?.attempts && s.run.attempts > 1 ? ` · ${w.attempts(s.run.attempts)}` : ""}
                          {s.run?.pending_approvals && runStatus !== "waiting_approval"
                            ? <> · <a href="/approvals">{w.queued(s.run.pending_approvals)}</a></> : null}
                          {s.run?.error && <div className="muted" style={{ whiteSpace: "normal" }}>{s.run.error}</div>}
                        </td>}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
          </div>
        )}
      </div>
    </div>
  );
}
