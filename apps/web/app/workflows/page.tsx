"use client";
// Read-only workflow view: the steps of a WorkflowSpec as a graph (columns = stages that can run
// in parallel) with the same steps as a table. Layout is computed here; no graph library needed.
// Picking a run draws the workflow that run saved, with where each step stands, and keeps it
// current while the run is going.
import { useEffect, useRef, useState } from "react";
import { api, problemsOf } from "../lib/api";
import { useI18n } from "../lib/i18n";
import { when } from "../lib/time";
import { Card, PageHeader } from "../components/shell";
import {
  Graph, POLL_MS, params, stepState,
  type RunSummary, type Version, type Workflow,
} from "./graph";
import { Editor } from "./editor";

export default function Workflows() {
  const { lang, t } = useI18n();
  const w = t.wf;
  const [list, setList] = useState<Workflow[]>([]);
  const [problems, setProblems] = useState<string[]>([]);
  const [models, setModels] = useState<Record<string, string>>({});
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
      setModels(r.models ?? {});
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

  const [versions, setVersions] = useState<Version[]>([]);
  const [viewed, setViewed] = useState<Workflow | null>(null);  // an older (or draft) version

  useEffect(() => {
    setViewed(null);
    if (!selected) return;
    api.workflowVersions(selected).then((r) => setVersions(r.versions)).catch(() => setVersions([]));
  }, [selected, lang]);

  const view = async (v: Version) => {
    setRunId("");
    setViewed(v.in_use ? null : await api.workflowVersion(selected, v.version));
  };

  const [editing, setEditing] = useState<Record<string, any> | null>(null);
  const [notice, setNotice] = useState<{ text: string; bad?: boolean } | null>(null);
  const [publishing, setPublishing] = useState(0);
  useEffect(() => { setEditing(null); setNotice(null); }, [selected]);

  const reload = async () => {
    const [d, v, l] = await Promise.all([api.workflow(selected), api.workflowVersions(selected), api.workflows()]);
    setDetail(d);
    setVersions(v.versions);
    setList(l.workflows);
  };
  const edit = async () => {
    if (!detail) return;
    setNotice(null);
    setEditing((await api.workflowVersion(selected, detail.version)).spec);
  };
  const publish = async (v: Version) => {
    setPublishing(v.version);
    try {
      await api.publishVersion(selected, v.version);
      setNotice({ text: t.wfEdit.published(v.version) });
      setViewed(null);
      await reload();
    } catch (e) {
      setNotice({ text: problemsOf(e).join(" · "), bad: true });
    } finally { setPublishing(0); }
  };

  const shown = overlay ?? viewed ?? detail;
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
                <span className="muted">
                  {x.category} · {x.source === "builtin" ? w.builtin : w.custom}{x.published_here ? ` · ${w.editedHere}` : ""}
                </span>
              </button>
            ))}
          </div>
        </Card>

        {shown?.steps && (
          <div className="stack" style={{ minWidth: 0 }}>
            {editing && detail?.steps && (
              <Editor spec={editing} steps={detail.steps} models={models} onClose={() => setEditing(null)}
                onSaved={async (version) => {
                  setEditing(null);
                  setNotice({ text: t.wfEdit.saved(version) });
                  await reload();
                }} />
            )}
            <Card title={shown.title}
              desc={`${shown.description} · ${w.version(shown.version)} · ${shown.hypotheses.join(", ")}`}
              actions={(runs.length > 0 || (!overlay && !viewed && !editing)) && (
                <div className="row">
                {!overlay && !viewed && !editing && (
                  <button className="ghost sm wf-edit-btn" onClick={edit}>{t.wfEdit.edit}</button>
                )}
                {runs.length > 0 && <label className="row" style={{ gap: 6 }}>
                  <span className="muted">{w.run}</span>
                  <select className="input" value={runId} onChange={(e) => { setViewed(null); setRunId(e.target.value); }}>
                    <option value="">{w.noRun}</option>
                    {runs.map((r) => (
                      <option key={r.run_id} value={r.run_id}>
                        {when(r.started_at, lang)}{r.workflow_version ? ` · v${r.workflow_version}` : ""} · {w.status[r.status] ?? r.status}
                      </option>
                    ))}
                  </select>
                </label>}
                </div>
              )}>
              {notice && (
                <div className="wf-runbar" role="status">
                  <span className={`badge ${notice.bad ? "red" : "green"}`} style={{ whiteSpace: "normal" }}>{notice.text}</span>
                </div>
              )}
              {viewed && !overlay && (
                <div className="wf-runbar">
                  <span className="badge amber">{w.viewing(viewed.version)}</span>
                  <button className="ghost sm" onClick={() => setViewed(null)}>{w.backToCurrent}</button>
                </div>
              )}
              {overlay?.run && (
                <div className="wf-runbar" aria-live="polite">
                  <span className={`badge ${w.badge[overlay.run.status] ?? ""}`}>{w.status[overlay.run.status] ?? overlay.run.status}</span>
                  <span className="muted">{overlay.run.scope} · {when(overlay.run.started_at, lang)} · <code>{overlay.run.run_id}</code></span>
                  {overlay.run.status === "waiting_approval" && <a href="/approvals">{w.toApprovals}</a>}
                  {overlay.run.budget_fallback && (
                    <a className="badge amber" href="/costs">{w.budgetFallback(overlay.run.budget_fallback.agent)}</a>
                  )}
                  {overlay.same_as_current === false && <span className="badge amber">{w.olderVersion}</span>}
                </div>
              )}
              <p className="muted" style={{ margin: "0 0 10px" }}>{w.graphHint}</p>
              <p className="muted wf-phone-note" style={{ margin: "0 0 10px" }}>{t.wfEdit.phoneReadOnly}</p>
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
                    <tr><th>{w.step}</th><th>{w.agent}</th><th>{w.waitsFor}</th><th>{w.params}</th><th>{w.required}</th><th>{w.tier}</th>{overlay && <th>{w.state}</th>}</tr>
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
                        <td>
                          <span className={s.model_tier === "fast" ? "badge accent tip" : "muted tip"}
                            data-tip={models[s.model_tier ?? "standard"] ?? ""}>{w.tierNames[s.model_tier ?? "standard"]}</span>
                        </td>
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
            {versions.length > 0 && (
              <Card title={w.versions} desc={w.versionsHint} flush>
                <div className="table-wrap">
                  <table className="wf-table">
                    <thead>
                      <tr><th>{w.versionCol}</th><th>{w.state}</th><th>{w.by}</th><th>{w.note}</th><th /></tr>
                    </thead>
                    <tbody>
                      {[...versions].reverse().map((v) => (
                        <tr key={v.version} className={shown.version === v.version && !overlay ? "wf-row-on" : ""}>
                          <td>v{v.version}{v.in_use && <span className="badge green" style={{ marginLeft: 6 }}>{w.inUse}</span>}</td>
                          <td>{w.versionStatus[v.status] ?? v.status}</td>
                          <td>{v.published_by
                            ? `${w.publishedBy(v.published_by)} · ${when(v.published_at, lang)}`
                            : v.created_by ? `${w.draftedBy(v.created_by)} · ${when(v.created_at, lang)}` : "–"}</td>
                          <td style={{ whiteSpace: "normal" }}>{v.note || <span className="muted">–</span>}</td>
                          <td><div className="row" style={{ flexWrap: "nowrap" }}>
                            <button className="ghost sm" onClick={() => view(v)}
                              aria-label={w.viewVersion(v.version)}>{w.view}</button>
                            {v.status === "draft" && (
                              <button className="sm wf-edit-btn" onClick={() => publish(v)} disabled={publishing !== 0}>
                                {publishing === v.version ? t.wfEdit.publishing : `${t.wfEdit.publish} v${v.version}`}
                              </button>
                            )}
                          </div></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </Card>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
