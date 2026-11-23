"use client";
// The role map (roadmap 9): who is Responsible, Accountable, Consulted and Informed for each kind
// of decision, in one project or all of them. GET/POST/DELETE /roles (changes need admin).
import { useEffect, useState } from "react";
import { api, errorText } from "../lib/api";
import { useI18n } from "../lib/i18n";
import { Card, PageHeader, ErrorCard } from "../components/shell";
import { Icon } from "../components/icons";

type Row = { id: number; kind: string; project_id: string | null; role: string; person: string };
const ROLES = ["R", "A", "C", "I"];
const KINDS = ["*", "gate", "budget", "allocation", "risk", "report", "schedule", "question",
  "workflow_publish", "model_recommendation"];

export default function Roles() {
  const { lang, t } = useI18n();
  const r = t.rolesp;
  const [rows, setRows] = useState<Row[] | null>(null);
  const [form, setForm] = useState({ kind: "gate", role: "A", person: "", project: "" });
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  const load = async () => {
    try { setRows(await api.roles()); setErr(""); } catch (e) { setErr(errorText(e)); }
  };
  useEffect(() => { load(); }, [lang]);  // eslint-disable-line react-hooks/exhaustive-deps

  const run = async (f: () => Promise<unknown>) => {
    setBusy(true); setErr("");
    try { await f(); await load(); } catch (e) { setErr(errorText(e)); } finally { setBusy(false); }
  };

  // one line per kind and project, a column per role
  const lines = new Map<string, { kind: string; project: string | null; byRole: Record<string, Row[]> }>();
  for (const row of rows ?? []) {
    const key = `${row.kind}|${row.project_id ?? ""}`;
    if (!lines.has(key)) lines.set(key, { kind: row.kind, project: row.project_id, byRole: {} });
    (lines.get(key)!.byRole[row.role] ??= []).push(row);
  }

  return (
    <div className="stack">
      <PageHeader title={t.nav.roles} desc={t.pages.roles}
        actions={<button className="ghost" onClick={load}><Icon.refresh />{t.common2.refresh}</button>} />
      {err && <ErrorCard label={t.common.error}>{err}</ErrorCard>}
      <Card title={r.add} desc={r.adminOnly}>
        <form className="row" style={{ gap: 8, flexWrap: "wrap" }} onSubmit={(e) => {
          e.preventDefault();
          run(() => api.assignRole({ ...form, project: form.project.trim() || undefined }));
          setForm((f) => ({ ...f, person: "" }));
        }}>
          <label className="row" style={{ gap: 6 }}><span className="muted">{r.kind}</span>
            <select className="input" value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value })}>
              {KINDS.map((k) => <option key={k} value={k}>{r.kinds[k] ?? k}</option>)}
            </select>
          </label>
          <label className="row" style={{ gap: 6 }}><span className="muted">{r.project}</span>
            <input className="input" value={form.project} placeholder={r.allProjects}
              onChange={(e) => setForm({ ...form, project: e.target.value })} />
          </label>
          <label className="row" style={{ gap: 6 }}><span className="muted">{r.role}</span>
            <select className="input" value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })}>
              {ROLES.map((x) => <option key={x} value={x}>{x} · {r.roleNames[x]}</option>)}
            </select>
          </label>
          <label className="row" style={{ gap: 6 }}><span className="muted">{r.person}</span>
            <input className="input" value={form.person} onChange={(e) => setForm({ ...form, person: e.target.value })} />
          </label>
          <button disabled={busy || !form.person.trim()}>{r.add}</button>
        </form>
      </Card>
      <Card title={r.map} flush>
        {rows && rows.length === 0 ? <div className="empty">{r.none}</div> : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr><th>{r.kind}</th><th>{r.project}</th>
                  {ROLES.map((x) => <th key={x}>{x} · {r.roleNames[x]}</th>)}</tr>
              </thead>
              <tbody>
                {[...lines.values()].map((l) => (
                  <tr key={`${l.kind}|${l.project ?? ""}`}>
                    <td style={{ whiteSpace: "nowrap" }}>{r.kinds[l.kind] ?? l.kind}</td>
                    <td style={{ whiteSpace: "nowrap" }}>{l.project ?? <span className="muted">{r.allProjects}</span>}</td>
                    {ROLES.map((x) => (
                      <td key={x}>
                        {(l.byRole[x] ?? []).map((row) => (
                          <span key={row.id} className="badge" style={{ marginRight: 4 }}>
                            {row.person}
                            <button className="ghost sm remove-x" aria-label={`${r.remove} ${row.person}`} disabled={busy}
                              onClick={() => run(() => api.removeRole(row.id))}>×</button>
                          </span>
                        ))}
                      </td>
                    ))}
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
