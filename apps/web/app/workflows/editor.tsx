"use client";
// The workflow editor: a form over the spec (add, remove, reorder steps; set what each waits for
// and its parameters), not a free canvas. Every change is checked by the server's validator, the
// same one a save and a publish pass; required steps of the version in use are locked here and
// refused by the server. A dry run tries the draft on the demo data before it is saved.
import { useEffect, useMemo, useRef, useState } from "react";
import { api, problemsOf, errorText } from "../lib/api";
import { useI18n } from "../lib/i18n";
import { Card } from "../components/shell";
import { Graph, params as paramsText, type Step } from "./graph";

type Row = {
  key: number; id: string; agent: string; needs: string[]; params: string; required: boolean;
  tier: "standard" | "fast";
  reads: NonNullable<Step["reads"]>;
};
type Agent = { id: string; name: string };
type DryRun = {
  ok: boolean; problems: string[]; error?: string | null; status?: string; scope?: string;
  steps?: { id: string; agent: string; status: string; pending_approvals: number; error?: string | null }[];
  approvals?: number; messages?: number;
};

let nextKey = 1;

// "gate=G2-planning, n=3" <-> {gate: "G2-planning", n: 3}
function parseParams(text: string): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const part of text.split(",").map((p) => p.trim()).filter(Boolean)) {
    const [k, ...rest] = part.split("=");
    const raw = rest.join("=").trim();
    try { out[k.trim()] = JSON.parse(raw); } catch { out[k.trim()] = raw; }
  }
  return out;
}

// the same stages the server computes (WorkflowSpec.levels); null when steps wait on each other
function levels(rows: Row[]): Record<string, number> | null {
  const level: Record<string, number> = {};
  let wave = 0;
  while (Object.keys(level).length < rows.length) {
    const ready = rows.filter((r) => !(r.id in level) && r.needs.every((n) => n in level && level[n] < wave));
    if (!ready.length) return null;
    ready.forEach((r) => { level[r.id] = wave; });
    wave += 1;
  }
  return level;
}

export function Editor({ spec, steps, models, onSaved, onClose }: {
  spec: Record<string, any>; steps: Step[]; models: Record<string, string>;
  onSaved: (version: number) => void; onClose: () => void;
}) {
  const { t } = useI18n();
  const w = t.wf;
  const e = t.wfEdit;
  const locked = useMemo(() => new Set(steps.filter((s) => s.required).map((s) => s.id)), [steps]);
  const [rows, setRows] = useState<Row[]>(() => steps.map((s) => ({
    key: nextKey++, id: s.id, agent: s.agent, needs: s.needs, params: paramsText(s.params), required: s.required,
    tier: s.model_tier ?? "standard", reads: s.reads ?? "isolated",
  })));
  const [agents, setAgents] = useState<Agent[]>([]);
  const [review, setReview] = useState<boolean>(Boolean(spec.review));
  const [note, setNote] = useState("");
  const [problems, setProblems] = useState<string[] | null>(null);
  const [dry, setDry] = useState<DryRun | null>(null);
  const [busy, setBusy] = useState("");
  const [msg, setMsg] = useState("");
  const live = useRef<HTMLDivElement>(null);

  useEffect(() => { api.agents().then((r) => setAgents(r.agents)).catch(() => {}); }, []);

  const draft = useMemo(() => ({
    ...spec,
    review,
    steps: rows.map((r) => ({
      id: r.id, agent: r.agent, needs: r.needs, params: parseParams(r.params), required: r.required,
      model_tier: r.tier === "fast" ? "fast" : null, reads: r.reads,
    })),
  }), [spec, rows, review]);

  // ask the server's validator a moment after the last change
  useEffect(() => {
    setProblems(null);
    setDry(null);
    const timer = setTimeout(() => {
      api.validateWorkflow(draft).then((r) => setProblems(r.problems)).catch((err) => setProblems([errorText(err)]));
    }, 350);
    return () => clearTimeout(timer);
  }, [draft]);

  const preview: Step[] | null = useMemo(() => {
    const lv = levels(rows);
    if (!lv || new Set(rows.map((r) => r.id)).size !== rows.length) return null;
    const names = Object.fromEntries(agents.map((a) => [a.id, a.name]));
    return rows.map((r) => ({
      id: r.id, agent: r.agent, agent_name: names[r.agent] ?? r.agent, params: parseParams(r.params),
      needs: r.needs, required: r.required, level: lv[r.id], model_tier: r.tier, reads: r.reads,
    }));
  }, [rows, agents]);

  const update = (key: number, change: Partial<Row>) =>
    setRows((rs) => rs.map((r) => {
      if (r.key === key) return { ...r, ...change };
      const old = rs.find((x) => x.key === key);
      // renaming a step keeps the steps that wait for it pointing at it
      return change.id !== undefined && old && r.needs.includes(old.id)
        ? { ...r, needs: r.needs.map((n) => (n === old.id ? change.id! : n)) } : r;
    }));
  const remove = (key: number) => setRows((rs) => {
    const gone = rs.find((r) => r.key === key)!;
    return rs.filter((r) => r.key !== key).map((r) => ({ ...r, needs: r.needs.filter((n) => n !== gone.id) }));
  });
  const move = (key: number, by: number) => setRows((rs) => {
    const i = rs.findIndex((r) => r.key === key), j = i + by;
    if (j < 0 || j >= rs.length) return rs;
    const out = [...rs];
    [out[i], out[j]] = [out[j], out[i]];
    return out;
  });
  const add = () => setRows((rs) => {
    let n = rs.length + 1;
    while (rs.some((r) => r.id === `step${n}`)) n += 1;
    const last = rs[rs.length - 1];
    return [...rs, { key: nextKey++, id: `step${n}`, agent: agents[0]?.id ?? "A2", needs: last ? [last.id] : [], params: "", required: false, tier: "standard", reads: "isolated" }];
  });
  const toggleNeed = (key: number, id: string) => setRows((rs) => rs.map((r) => (r.key !== key ? r
    : { ...r, needs: r.needs.includes(id) ? r.needs.filter((n) => n !== id) : [...r.needs, id] })));

  const say = (text: string) => { setMsg(text); setTimeout(() => live.current?.focus(), 0); };
  const runDry = async () => {
    setBusy("dry"); setMsg("");
    try { setDry(await api.dryRun(draft)); } catch (err: any) { say(problemsOf(err).join(" · ")); } finally { setBusy(""); }
  };
  const save = async () => {
    setBusy("save"); setMsg("");
    try {
      const saved = await api.saveDraft(spec.id, draft, note);
      onSaved(saved.version);
    } catch (err: any) { say(problemsOf(err).join(" · ")); } finally { setBusy(""); }
  };

  const ok = problems !== null && problems.length === 0;
  return (
    <Card title={e.title(spec.id)} desc={e.desc} className="wf-edit-only"
      actions={<button className="ghost sm" onClick={onClose}>{e.cancel}</button>}>
      <label className="check wf-review">
        <input type="checkbox" checked={review} onChange={(ev) => setReview(ev.target.checked)} />{" "}
        <span className="tip" data-tip={t.rv.reviewTip}>{t.rv.review}</span>
      </label>
      <div className="wf-rows" role="list" aria-label={w.graph}>
        {rows.map((r, i) => {
          const lock = locked.has(r.id) && steps.some((s) => s.id === r.id && s.agent === r.agent);
          const others = rows.filter((o) => o.key !== r.key);
          return (
            <div key={r.key} className={`wf-row ${lock ? "locked" : ""}`} role="listitem">
              <div className="wf-row-head">
                <b>{i + 1}</b>
                <label><span>{w.step}</span>
                  <input className="input" value={r.id} disabled={lock} aria-label={`${w.step} ${i + 1}`}
                    onChange={(ev) => update(r.key, { id: ev.target.value.trim() })} />
                </label>
                <label><span>{w.agent}</span>
                  <select className="input" value={r.agent} disabled={lock} onChange={(ev) => update(r.key, { agent: ev.target.value })}>
                    {!agents.some((a) => a.id === r.agent) && <option value={r.agent}>{r.agent}</option>}
                    {agents.map((a) => <option key={a.id} value={a.id}>{a.id} · {a.name}</option>)}
                  </select>
                </label>
                <label className="grow"><span>{w.params}</span>
                  <input className="input" value={r.params} disabled={lock} placeholder={e.paramsHint}
                    onChange={(ev) => update(r.key, { params: ev.target.value })} />
                </label>
                <label><span>{w.tier}</span>
                  <select className="input" value={r.tier} aria-label={`${w.tier} ${r.id}`}
                    onChange={(ev) => update(r.key, { tier: ev.target.value as Row["tier"] })}>
                    {(["standard", "fast"] as const).map((t) => (
                      <option key={t} value={t}>{w.tierNames[t]}{models[t] ? ` · ${models[t]}` : ""}</option>
                    ))}
                  </select>
                </label>
                <label><span className="tip" data-tip={t.rv.readsTip}>{t.rv.reads}</span>
                  <select className="input" value={r.reads} aria-label={`${t.rv.reads} ${r.id}`}
                    onChange={(ev) => update(r.key, { reads: ev.target.value as Row["reads"] })}>
                    {(["isolated", "upstream", "board"] as const).map((m) => (
                      <option key={m} value={m}>{t.rv.readsNames[m]}</option>
                    ))}
                  </select>
                </label>
                <label className="check"><input type="checkbox" checked={r.required} disabled={lock}
                  onChange={(ev) => update(r.key, { required: ev.target.checked })} /> {w.required}</label>
                <div className="row">
                  <button className="ghost sm" onClick={() => move(r.key, -1)} disabled={i === 0} aria-label={e.moveUp(r.id)}>↑</button>
                  <button className="ghost sm" onClick={() => move(r.key, 1)} disabled={i === rows.length - 1} aria-label={e.moveDown(r.id)}>↓</button>
                  <button className="ghost sm" onClick={() => remove(r.key)} disabled={lock} aria-label={e.remove(r.id)}>{e.removeShort}</button>
                </div>
              </div>
              <fieldset className="wf-needs">
                <legend>{w.waitsFor}</legend>
                {others.length === 0 && <span className="muted">{w.start}</span>}
                {others.map((o) => (
                  <label key={o.key} className="check">
                    <input type="checkbox" checked={r.needs.includes(o.id)} onChange={() => toggleNeed(r.key, o.id)} /> {o.id}
                  </label>
                ))}
                {lock && <span className="badge amber tip" data-tip={e.lockedTip}>{e.locked}</span>}
              </fieldset>
            </div>
          );
        })}
      </div>
      <div className="row" style={{ margin: "10px 0 14px" }}>
        <button className="ghost sm" onClick={add}>{e.addStep}</button>
      </div>

      <div className="wf-check" aria-live="polite">
        {problems === null ? <span className="muted">{e.checking}</span>
          : ok ? <span className="badge green">{e.valid}</span>
            : <ul>{problems.map((p) => <li key={p}>{p}</li>)}</ul>}
      </div>
      {preview && <Graph steps={preview} active="" setActive={() => {}} />}

      <label className="wf-note"><span>{e.note}</span>
        <input className="input" value={note} placeholder={e.notePlaceholder} onChange={(ev) => setNote(ev.target.value)} />
      </label>
      <div className="row" style={{ marginTop: 10 }}>
        <button className="ghost" onClick={runDry} disabled={!ok || busy !== ""}>{busy === "dry" ? e.dryRunning : e.dryRun}</button>
        <button onClick={save} disabled={!ok || busy !== ""}>{busy === "save" ? e.saving : e.saveDraft}</button>
        <span className="muted">{e.publishLater}</span>
      </div>
      {msg && <div ref={live} tabIndex={-1} className="wf-check" style={{ color: "var(--red)" }}>{msg}</div>}

      {dry && (
        <div className="wf-dry" aria-live="polite">
          <h3>{e.dryTitle}</h3>
          <p className="muted">{e.dryNote(dry.scope ?? "")}</p>
          {dry.problems.length > 0 ? <ul>{dry.problems.map((p) => <li key={p}>{p}</li>)}</ul> : (
            <>
              <div className="row">
                <span className={`badge ${w.badge[dry.status ?? ""] ?? ""}`}>{w.status[dry.status ?? ""] ?? dry.status}</span>
                <span className="muted">{e.dryCounts(dry.messages ?? 0, dry.approvals ?? 0)}</span>
              </div>
              {dry.error && <p style={{ color: "var(--red)" }}>{dry.error}</p>}
              <ol>
                {dry.steps?.map((s) => (
                  <li key={s.id}><code>{s.id}</code> · {s.agent} · {w.status[s.status] ?? s.status}
                    {s.pending_approvals ? ` · ${w.queued(s.pending_approvals)}` : ""}</li>
                ))}
              </ol>
            </>
          )}
        </div>
      )}
    </Card>
  );
}
