"use client";
// The guardrail log (roadmap 10): every check, what it found and what took effect; filter to
// what a guardrail in observe mode would have blocked. GET /guardrails.
import { useEffect, useState } from "react";
import { api, errorText } from "../lib/api";
import { useI18n } from "../lib/i18n";
import { clock } from "../lib/time";
import { Card, PageHeader, ErrorCard } from "../components/shell";
import { Icon } from "../components/icons";

type Entry = { id: number; name: string; point: string; mode: string; decision: string; outcome: string;
  reason: string; run_id: string | null; created_at: string };

const TONE: Record<string, string> = { allow: "green", modify: "accent", ask: "amber", block: "red" };

export default function GuardrailLog() {
  const { lang, t } = useI18n();
  const g = t.glog;
  const [rows, setRows] = useState<Entry[] | null>(null);
  const [names, setNames] = useState<string[]>([]);
  const [name, setName] = useState("");
  const [found, setFound] = useState(false);
  const [err, setErr] = useState("");

  const load = async () => {
    try {
      const all: Entry[] = await api.guardrailLog({ name: name || undefined, limit: 500 });
      setRows(found ? all.filter((r) => r.outcome !== "allow") : all);
      setErr("");
    } catch (e) { setErr(errorText(e)); }
  };
  useEffect(() => { load(); }, [name, found, lang]);  // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    api.policy().then((p: { guardrails: { name: string }[] }) => setNames(p.guardrails.map((x) => x.name))).catch(() => {});
  }, []);

  return (
    <div className="stack">
      <PageHeader title={t.nav.guardrails} desc={t.pages.guardrails}
        actions={<button className="ghost" onClick={load}><Icon.refresh />{t.common2.refresh}</button>} />
      {err && <ErrorCard label={t.common.error}>{err}</ErrorCard>}
      <Card>
        <div className="row" style={{ gap: 12, flexWrap: "wrap" }}>
          <label className="row" style={{ gap: 6 }}>
            <span className="muted">{t.pol.name}</span>
            <select className="input" value={name} onChange={(e) => setName(e.target.value)}>
              <option value="">{g.all}</option>
              {names.map((n) => <option key={n} value={n}>{n}</option>)}
            </select>
          </label>
          <label className="row check-target" style={{ gap: 6 }}>
            <input type="checkbox" checked={found} onChange={(e) => setFound(e.target.checked)} />
            <span>{g.wouldBlock}</span>
          </label>
        </div>
      </Card>
      <Card flush>
        {rows && rows.length === 0 ? <div className="empty">{g.none}</div> : (
          <div className="table-wrap">
            <table>
              <thead><tr><th>{g.time}</th><th>{t.pol.name}</th><th>{t.pol.point}</th><th>{t.pol.mode}</th>
                <th>{g.found}</th><th>{g.effect}</th><th>{g.reason}</th><th>{g.run}</th></tr></thead>
              <tbody>
                {(rows ?? []).map((r) => (
                  <tr key={r.id}>
                    <td className="muted" style={{ whiteSpace: "nowrap" }}>{clock(r.created_at, lang)}</td>
                    <td><code>{r.name}</code></td>
                    <td>{r.point}</td>
                    <td style={{ whiteSpace: "nowrap" }}>{t.pol.modes[r.mode] ?? r.mode}</td>
                    <td><span className={`badge ${TONE[r.outcome] ?? ""}`}>{r.outcome}</span></td>
                    <td><span className={`badge ${TONE[r.decision] ?? ""}`}>{r.decision}</span></td>
                    <td className="wrap">{r.reason}</td>
                    <td>{r.run_id ? <code title={r.run_id}>{r.run_id.slice(0, 8)}</code> : <span className="muted">–</span>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
