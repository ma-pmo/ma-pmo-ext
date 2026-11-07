"use client";
// Read-only workflow view: the steps of a WorkflowSpec as a graph (columns = stages that can run
// in parallel) with the same steps as a table. Layout is computed here; no graph library needed.
import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { useI18n } from "../lib/i18n";
import { Card, PageHeader } from "../components/shell";

type Step = {
  id: string; agent: string; agent_name: string; params: Record<string, unknown>;
  needs: string[]; required: boolean; level: number;
};
type Workflow = {
  id: string; version: number; title: string; category: string; description: string;
  hypotheses: string[]; source: "builtin" | "custom"; agents: string[]; steps?: Step[];
};

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

function Graph({ steps, active, setActive }: { steps: Step[]; active: string; setActive: (id: string) => void }) {
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
              className={`wf-node ${s.required ? "required" : ""} ${active === s.id ? "on" : ""}`}
              aria-label={w.nodeLabel(s.id, s.agent_name, s.needs, s.required)}
              onFocus={() => setActive(s.id)} onMouseEnter={() => setActive(s.id)} onClick={() => setActive(s.id)}>
              <rect width={W} height={H} rx="10" />
              <text x="12" y="23" className="wf-title">{s.agent} · {s.agent_name}</text>
              <text x="12" y="44" className="wf-sub">
                {clip(`${s.id}${Object.keys(s.params).length ? ` · ${params(s.params)}` : ""}`, 28)}
              </text>
              {s.required && <text x={W - 10} y="23" textAnchor="end" className="wf-lock">{w.required}</text>}
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

  useEffect(() => {
    api.workflows().then((r) => {
      setList(r.workflows);
      setProblems(r.problems);
      const wanted = new URLSearchParams(window.location.search).get("id");
      setSelected((cur) => cur || (r.workflows.some((x: Workflow) => x.id === wanted) ? wanted! : r.workflows[0]?.id || ""));
    }).catch((e) => setErr(String(e.message || e)));
  }, [lang]);

  useEffect(() => {
    if (!selected) return;
    setActive("");
    api.workflow(selected).then(setDetail).catch((e) => setErr(String(e.message || e)));
    window.history.replaceState(null, "", `?id=${encodeURIComponent(selected)}`);
    // bring the chosen item into the list's own view without scrolling the page
    const item = document.querySelector<HTMLElement>(".wf-list button.on");
    const box = item?.parentElement;
    if (item && box && (item.offsetTop < box.scrollTop || item.offsetTop > box.scrollTop + box.clientHeight - item.offsetHeight)) {
      box.scrollTop = item.offsetTop - box.clientHeight / 2;
    }
  }, [selected, lang]);

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

        {detail?.steps && (
          <div className="stack" style={{ minWidth: 0 }}>
            <Card title={detail.title}
              desc={`${detail.description} · ${w.version(detail.version)} · ${detail.hypotheses.join(", ")}`}>
              <p className="muted" style={{ margin: "0 0 10px" }}>{w.graphHint}</p>
              <Graph steps={detail.steps} active={active} setActive={setActive} />
            </Card>
            <Card title={w.table} flush>
              <div className="table-wrap">
                <table className="wf-table">
                  <thead>
                    <tr><th>{w.step}</th><th>{w.agent}</th><th>{w.waitsFor}</th><th>{w.params}</th><th>{w.required}</th></tr>
                  </thead>
                  <tbody>
                    {detail.steps.map((s) => (
                      <tr key={s.id} className={active === s.id ? "wf-row-on" : ""}>
                        <td><code>{s.id}</code></td>
                        <td>{s.agent} · {s.agent_name}</td>
                        <td>{s.needs.length ? s.needs.join(", ") : <span className="muted">{w.start}</span>}</td>
                        <td>{Object.keys(s.params).length ? <code>{params(s.params)}</code> : <span className="muted">–</span>}</td>
                        <td>{s.required
                          ? <span className="badge amber tip" data-tip={w.requiredTip}>{w.required}</span>
                          : <span className="muted">–</span>}</td>
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
