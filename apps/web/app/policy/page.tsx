"use client";
// The policy (roadmap 10): the stop switch, each guardrail's mode, the workspace tolerances,
// the version history, and the evidence pack. GET/PUT /policy, /tolerances, /stop; GET /evidence.
import { useEffect, useState } from "react";
import { api, errorText } from "../lib/api";
import { useI18n } from "../lib/i18n";
import { when } from "../lib/time";
import { Card, PageHeader, ErrorCard } from "../components/shell";
import { Icon } from "../components/icons";

type Guard = { name: string; point: string; mode: string; description: string };
type Policy = { version: number; guardrails: Guard[]; tolerances: Record<string, any>;
  stop: { all?: boolean; agents?: string[]; notifiers?: string[] } };
type Version = { version: number; created_by: string; created_at: string; note: string };

const MODES = ["off", "observe", "enforce"];
const LIMITS = ["max_slip_days", "min_spi", "max_severity", "max_unstaffed_pct"];
const SEVERITY = ["low", "medium", "high", "critical"];
const MODE_TONE: Record<string, string> = { off: "", observe: "amber", enforce: "green" };

export default function PolicyPage() {
  const { lang, t } = useI18n();
  const p = t.pol;
  const [pol, setPol] = useState<Policy | null>(null);
  const [versions, setVersions] = useState<Version[]>([]);
  const [limits, setLimits] = useState<Record<string, string>>({});
  const [span, setSpan] = useState({ since: "", until: "" });
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  const load = async () => {
    try {
      const now: Policy = await api.policy();
      setPol(now);
      setVersions(await api.policyVersions());
      const ws = now.tolerances?.workspace ?? {};
      setLimits(Object.fromEntries(LIMITS.map((k) => [k, ws[k] === undefined ? "" : String(ws[k])])));
      setErr("");
    } catch (e) { setErr(errorText(e)); }
  };
  useEffect(() => { load(); }, [lang]);  // eslint-disable-line react-hooks/exhaustive-deps

  const run = async (f: () => Promise<unknown>) => {
    setBusy(true); setErr("");
    try { await f(); await load(); } catch (e) { setErr(errorText(e)); } finally { setBusy(false); }
  };

  const saveLimits = () => run(() => {
    const workspace: Record<string, unknown> = {};
    for (const k of LIMITS) {
      const v = limits[k]?.trim();
      if (v) workspace[k] = k === "max_severity" ? v : Number(v);
    }
    return api.setTolerances({ ...(pol?.tolerances ?? {}), workspace });
  });

  const download = async (format: "md" | "json") => {
    const res = await api.evidence(format, span.since || undefined, span.until || undefined);
    const name = /filename="([^"]+)"/.exec(res.headers.get("content-disposition") || "")?.[1]
      || `evidence.${format}`;
    const url = URL.createObjectURL(await res.blob());
    Object.assign(document.createElement("a"), { href: url, download: name }).click();
    URL.revokeObjectURL(url);
  };

  const stop = pol?.stop ?? {};
  const overrides = [
    ...Object.entries(pol?.tolerances?.portfolios ?? {}).map(([k, v]) => [`portfolio ${k}`, v]),
    ...Object.entries(pol?.tolerances?.projects ?? {}).map(([k, v]) => [`project ${k}`, v]),
  ] as [string, Record<string, unknown>][];

  return (
    <div className="stack">
      <PageHeader title={t.nav.policy} desc={t.pages.policy}
        actions={<button className="ghost" onClick={load}><Icon.refresh />{t.common2.refresh}</button>} />
      {err && <ErrorCard label={t.common.error}>{err}</ErrorCard>}

      <Card title={p.stopTitle} desc={pol ? `${p.version(pol.version)} · ${p.adminOnly}` : p.adminOnly}>
        <div className="row" style={{ gap: 10, flexWrap: "wrap" }}>
          <span className={`badge ${stop.all ? "red" : "green"}`}>{stop.all ? p.stopOn : p.stopOff}</span>
          {stop.agents?.length ? <span className="muted">{p.stoppedAgents(stop.agents.join(", "))}</span> : null}
          <button className={stop.all ? "" : "ghost"} disabled={busy} onClick={() => {
            if (!stop.all && !window.confirm(p.confirmStop)) return;
            run(() => api.setStop({ all: !stop.all, agents: stop.agents ?? [], notifiers: stop.notifiers ?? [] }));
          }}>{stop.all ? p.resume : p.stopAll}</button>
        </div>
      </Card>

      <Card title={p.guardrails} flush>
        <div className="table-wrap">
          <table>
            <thead><tr><th>{p.name}</th><th>{p.point}</th><th>{p.mode}</th><th>{p.what}</th></tr></thead>
            <tbody>
              {(pol?.guardrails ?? []).map((g) => (
                <tr key={g.name}>
                  <td><code>{g.name}</code></td>
                  <td>{g.point}</td>
                  <td>
                    <label className="sr-only" htmlFor={`mode-${g.name}`}>{p.mode} {g.name}</label>
                    <select id={`mode-${g.name}`} className={`input mode-${MODE_TONE[g.mode] || "off"}`} value={g.mode}
                      disabled={busy} onChange={(e) => run(() => api.changePolicy({ [g.name]: { mode: e.target.value } }))}>
                      {MODES.map((m) => <option key={m} value={m}>{p.modes[m]}</option>)}
                    </select>
                  </td>
                  <td className="muted wrap">{p.desc[g.name] ?? g.description}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <Card title={p.tolerances} desc={p.tolerancesHint}>
        <form className="row" style={{ gap: 10, flexWrap: "wrap" }} onSubmit={(e) => { e.preventDefault(); saveLimits(); }}>
          {LIMITS.map((k) => (
            <label key={k} className="row" style={{ gap: 6 }}>
              <span className="muted">{p.limits[k]}</span>
              {k === "max_severity" ? (
                <select className="input" value={limits[k] ?? ""} onChange={(e) => setLimits({ ...limits, [k]: e.target.value })}>
                  <option value="">{p.none}</option>
                  {SEVERITY.map((s) => <option key={s} value={s}>{s}</option>)}
                </select>
              ) : (
                <input className="input" style={{ width: 90 }} inputMode="decimal" value={limits[k] ?? ""}
                  placeholder={p.none} onChange={(e) => setLimits({ ...limits, [k]: e.target.value })} />
              )}
            </label>
          ))}
          <button disabled={busy}>{p.save}</button>
        </form>
        {overrides.length > 0 && (
          <div style={{ marginTop: 10 }}>
            <b>{p.overrides}</b>
            <ul className="dlog-list">{overrides.map(([level, v]) => (
              <li key={level}>{level}: {Object.entries(v).map(([k, x]) => `${p.limits[k] ?? k} ${x}`).join(", ")}</li>
            ))}</ul>
          </div>
        )}
      </Card>

      <Card title={p.evidence} desc={p.evidenceHint}>
        <div className="row" style={{ gap: 10, flexWrap: "wrap" }}>
          <label className="row" style={{ gap: 6 }}><span className="muted">{p.from}</span>
            <input className="input" type="date" value={span.since} onChange={(e) => setSpan({ ...span, since: e.target.value })} />
          </label>
          <label className="row" style={{ gap: 6 }}><span className="muted">{p.to}</span>
            <input className="input" type="date" value={span.until} onChange={(e) => setSpan({ ...span, until: e.target.value })} />
          </label>
          <button className="ghost" onClick={() => download("md")}><Icon.download /> Markdown</button>
          <button className="ghost" onClick={() => download("json")}><Icon.download /> JSON</button>
        </div>
      </Card>

      <Card title={p.versions} flush>
        <ul className="inbox-list">
          {versions.length === 0 && <li className="muted">{p.version(0)}</li>}
          {versions.map((v) => (
            <li key={v.version}>
              <b>{p.version(v.version)}</b>
              <span className="muted">{v.created_by} · {when(v.created_at, lang)}{v.note ? ` · ${v.note}` : ""}</span>
            </li>
          ))}
        </ul>
      </Card>
    </div>
  );
}
