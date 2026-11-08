"use client";
// The workflow graph: columns are stages that can run in parallel, arrows point to the step that
// waits. Layout is computed here; no graph library needed. Shared by the view and the editor.
import { useI18n } from "../lib/i18n";

export type StepRun = {
  status: string; attempts?: number; error?: string | null; pending_approvals: number;
  started_at?: string | null; finished_at?: string | null;
};
export type Step = {
  id: string; agent: string; agent_name: string; params: Record<string, unknown>;
  needs: string[]; required: boolean; level: number; run?: StepRun;
  model_tier?: "standard" | "fast";
};
export type RunSummary = {
  run_id: string; kind: string; workflow: string; scope: string; status: string; started_at: string;
  workflow_version?: number | null;
  budget_fallback?: { kind: string; agent: string; step: number | null } | null;
};
export type Version = {
  version: number; status: "builtin" | "file" | "draft" | "published"; note: string; in_use: boolean;
  created_by: string | null; created_at: string | null; published_by: string | null; published_at: string | null;
};
export type Workflow = {
  id: string; version: number; title: string; category: string; description: string;
  hypotheses: string[]; source: "builtin" | "custom"; agents: string[]; steps?: Step[];
  published_here?: boolean;
  run?: RunSummary; same_as_current?: boolean;
};

export const POLL_MS = 2000;
// In a paused run, a step that queued an approval is what the run waits on. A run that did not
// pause has finished that step; its approvals are only waiting in the queue.
export const stepState = (r: StepRun | undefined, run: string | undefined) =>
  (!r ? "" : r.pending_approvals > 0 && run === "waiting_approval" ? "waiting_approval" : r.status);

const W = 188, H = 60, GAP_X = 64, GAP_Y = 16, PAD = 10;

export function layout(steps: Step[]) {
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

export const params = (p: Record<string, unknown>) =>
  Object.entries(p).map(([k, v]) => `${k}=${typeof v === "string" ? v : JSON.stringify(v)}`).join(", ");

// the table shows the full text; a node keeps one line
const clip = (text: string, n: number) => (text.length > n ? `${text.slice(0, n - 1)}…` : text);

export function Graph({ steps, active, setActive, runStatus }: {
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
                {clip(`${s.model_tier === "fast" ? `${w.tierShort.fast} · ` : ""}${s.id}${Object.keys(s.params).length ? ` · ${params(s.params)}` : ""}`, 28)}
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
