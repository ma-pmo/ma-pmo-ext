"use client";
import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { useI18n } from "../lib/i18n";
import { Card, PageHeader, Stat, ErrorCard } from "../components/shell";
import { Icon } from "../components/icons";

const ENV_EXAMPLE = `MA_PMO_INTEGRATIONS=slack,github      # trackers: jira | github | linear
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...
GITHUB_REPOS=acme/api,acme/web
GITHUB_TOKEN=github_pat_...
MA_PMO_CALENDAR_DIR=./calendars       # <resource_id>.ics per person
MA_PMO_RETRIEVER=vector               # A7 vector search
MA_PMO_AUTH_MODE=api_key              # see docs/AUTH.md`;

export default function Integrations() {
  const { lang, t } = useI18n();
  const g = t.integ;
  const [rows, setRows] = useState<any[]>([]);
  const [err, setErr] = useState("");
  const [result, setResult] = useState<Record<string, { ok: boolean; text: string }>>({});
  const [busy, setBusy] = useState("");
  const [sys, setSys] = useState<any>(null);

  async function load() {
    try {
      setRows(await api.integrations());
      setSys(await api.system());
      setErr("");
    }
    catch (x: any) { setErr(String(x.message || x)); }
  }
  useEffect(() => { load(); }, [lang]);

  async function test(name: string) {
    setBusy(name);
    try {
      const r = await api.testIntegration(name);
      setResult((s) => ({ ...s, [name]: { ok: r.ok, text: r.ok ? g.testOk : `${g.testFail}: ${r.results?.[0]?.error ?? ""}` } }));
    } catch (x: any) {
      setResult((s) => ({ ...s, [name]: { ok: false, text: `${g.testFail}: ${String(x.message || x).slice(0, 160)}` } }));
    } finally { setBusy(""); }
  }

  const kindLabel = (k: string) => (k === "notifier" ? g.notifier : k === "tracker" ? g.tracker : g.unknown);
  const active = rows.filter((r) => r.active).length;

  return (
    <div className="stack">
      <PageHeader
        title={t.nav.integrations}
        desc={t.pages.integrations}
        actions={<button className="ghost" onClick={load}><Icon.refresh />{t.common2.refresh}</button>}
      />
      {err && <ErrorCard label={t.common.apiError}>{err}</ErrorCard>}

      <div className="grid cols-3">
        <Stat icon={<Icon.integrations />} label={g.table} value={rows.length} />
        <Stat icon={<Icon.approvals />} label={g.enabled} value={rows.filter((r) => r.enabled).length} />
        <Stat icon={<Icon.trend />} label={g.configured} value={active} />
      </div>

      <Card flush title={g.table}>
        <div className="table-wrap">
          <table>
            <thead><tr><th>{g.name}</th><th>{g.kind}</th><th>{g.enabled}</th><th>{g.configured}</th><th>{g.missing}</th><th /></tr></thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.name}>
                  <td><b>{r.name}</b><div className="muted">{r.description}</div></td>
                  <td><span className={`badge ${r.kind === "notifier" ? "accent" : r.kind === "tracker" ? "purple" : ""}`}>{kindLabel(r.kind)}</span></td>
                  <td><span className={`badge ${r.enabled ? "green" : ""}`}>{r.enabled ? t.common2.yes : t.common2.no}</span></td>
                  <td><span className={`badge ${r.configured ? "green" : r.enabled ? "red" : ""}`}>{r.configured ? t.common2.yes : t.common2.no}</span></td>
                  <td>{(r.missing_env ?? []).length ? r.missing_env.map((m: string) => <code key={m} style={{ marginRight: 6 }}>{m}</code>) : "–"}</td>
                  <td>
                    {r.kind === "notifier" && (
                      <button className="sm ghost" onClick={() => test(r.name)} disabled={!r.configured || busy === r.name}>{g.test}</button>
                    )}
                    {result[r.name] && <div className="muted" style={{ color: result[r.name].ok ? "var(--green)" : "var(--red)", marginTop: 4 }}>{result[r.name].text}</div>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      {sys && (
        <Card flush title={g.platform} desc={g.platformDesc} actions={<span className="badge">v{sys.version}</span>}>
          <div className="table-wrap">
            <table>
              <tbody>
                {[
                  [g.auth, sys.auth.mode === "off"
                    ? <span className="badge amber">{g.authOff}</span>
                    : <span className="badge green">{g.authOn(sys.auth.mode)}</span>, "MA_PMO_AUTH_MODE"],
                  [g.tracing, <span className={`badge ${sys.tracing.enabled ? "green" : ""}`}>{sys.tracing.enabled ? `${g.on} · ${sys.tracing.exporter}` : g.off}</span>, "OTEL_ENABLED"],
                  [g.retrieverName, <span className={`badge ${sys.retriever.mode === "vector" ? "green" : ""}`}>{sys.retriever.mode === "vector" ? g.vector(sys.retriever.model) : g.lexical}</span>, "MA_PMO_RETRIEVER"],
                  [g.calendars, <span className={`badge ${sys.calendar.configured ? "green" : ""}`}>{sys.calendar.configured ? g.on : g.off}</span>, "MA_PMO_CALENDAR_DIR"],
                  [g.mcp, <span className={`badge ${sys.mcp.installed ? "green" : ""}`}>{sys.mcp.installed ? g.installed : g.notInstalled}</span>, "ma-pmo mcp"],
                ].map(([label, value, hint]) => (
                  <tr key={String(hint)}><td><b>{label}</b></td><td>{value}</td><td className="muted"><code>{hint}</code></td></tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      <Card title={g.howTo} desc={g.howToDesc}>
        <pre className="code">{ENV_EXAMPLE}</pre>
        <div className="muted" style={{ marginTop: 8 }}>
          <a href={`https://github.com/ma-pmo/ma-pmo-ext/blob/main/docs/INTEGRATIONS${lang === "ko" ? ".ko" : ""}.md`} target="_blank" rel="noreferrer" className="tap-link">{g.guide}</a>
        </div>
      </Card>
    </div>
  );
}
