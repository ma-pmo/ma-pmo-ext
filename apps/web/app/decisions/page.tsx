"use client";
// The decision log: every decision in MADR order (context, drivers, options, outcome,
// consequences), with who decided, whom they consulted and whom they told. GET /decisions; one
// record's PROV-JSON downloads from GET /decisions/{id}/provenance. See docs/REVIEW.md.
import { useEffect, useState } from "react";
import { api, errorText } from "../lib/api";
import { useI18n } from "../lib/i18n";
import { when } from "../lib/time";
import { Card, PageHeader, ErrorCard } from "../components/shell";
import { Icon } from "../components/icons";

type Who = { who: string; role: string; constraint?: string; verdict?: string };
// a notification attempt (communication log), or a person the roles say to inform (roadmap 9)
type Told = { channel?: string; event?: string; status?: string; error?: string | null; at?: string;
  who?: string; role?: string };
type Rec = {
  id: string; kind: string; subject: string; title: string; status: string; context: string | null;
  drivers: { kind: string; ref: string; field?: string }[];
  options: { option: string; message_id?: string }[];
  outcome: { chosen?: string; justification?: string | null };
  decision_makers: Who[]; consulted: Who[]; informed: Told[]; consequences: string[];
  supersedes: string | null; run_id: string | null; message_id: string | null;
  approval_id: number | null; created_at: string; updated_at: string;
};

type Owed = { id: string; consequent: string; state: string; debtor: string; creditor: string;
  due: string | null; history: { op: string; by: string; at: string; note: string }[] };

const KINDS = ["gate", "report", "risk", "allocation", "schedule", "workflow_publish",
  "model_recommendation", "budget"];
const STATUSES = ["proposed", "committed", "accepted", "rejected", "superseded"];
const TONE: Record<string, string> = { committed: "green", accepted: "green", rejected: "red",
  proposed: "amber", superseded: "" };
const SENT: Record<string, string> = { sent: "green", failed: "red", skipped: "" };

export default function Decisions() {
  const { lang, t } = useI18n();
  const d = t.dlog;
  const [kind, setKind] = useState("");
  const [status, setStatus] = useState("");
  const [subject, setSubject] = useState("");
  const [rows, setRows] = useState<Rec[] | null>(null);
  const [picked, setPicked] = useState("");
  const [rec, setRec] = useState<Rec | null>(null);
  const [owed, setOwed] = useState<Owed[]>([]);
  const [err, setErr] = useState("");

  const load = async () => {
    try {
      const list: Rec[] = await api.decisions({ kind, status, subject: subject.trim(), limit: 200 });
      setRows(list); setErr("");
      const want = new URLSearchParams(window.location.search).get("id") || picked;
      setPicked(list.some((x) => x.id === want) ? want : list[0]?.id ?? "");
    } catch (e) { setErr(errorText(e)); }
  };
  useEffect(() => { load(); }, [kind, status, lang]);  // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!picked) { setRec(null); return; }
    api.decision(picked).then(setRec).catch((e) => setErr(errorText(e)));
    api.commitments({ decision: picked }).then(setOwed).catch(() => setOwed([]));
  }, [picked, lang]);

  const downloadProv = async () => {
    if (!rec) return;
    const res = await api.decisionProvenance(rec.id);
    const url = URL.createObjectURL(new Blob([await res.text()], { type: "application/json" }));
    Object.assign(document.createElement("a"), { href: url, download: `${rec.id}.prov.json` }).click();
    URL.revokeObjectURL(url);
  };

  const people = (list: Who[]) => list.length === 0 ? <span className="muted">–</span> : (
    <ul className="dlog-list">
      {list.map((w, i) => (
        <li key={i}>
          <b>{w.who}</b> <span className="muted">{t.rv.role[w.role] ?? w.role}</span>
          {w.constraint && <> · {t.rv.constraint[w.constraint] ?? w.constraint}</>}
          {w.verdict && <> <span className={`badge ${w.verdict === "VERIFIED" ? "green" : w.verdict === "CHALLENGE" ? "red" : "accent"}`}>{w.verdict}</span></>}
        </li>
      ))}
    </ul>
  );

  return (
    <div className="stack">
      <PageHeader title={t.nav.decisions} desc={t.pages.decisions}
        actions={<button className="ghost" onClick={load}><Icon.refresh />{t.common2.refresh}</button>} />
      {err && <ErrorCard label={t.common.error}>{err}</ErrorCard>}
      <Card>
        <form className="row" style={{ gap: 12, flexWrap: "wrap" }} onSubmit={(e) => { e.preventDefault(); load(); }}>
          <label className="row" style={{ gap: 6 }}>
            <span className="muted">{d.kind}</span>
            <select className="input" value={kind} onChange={(e) => setKind(e.target.value)}>
              <option value="">{d.all}</option>
              {KINDS.map((k) => <option key={k} value={k}>{d.kinds[k]}</option>)}
            </select>
          </label>
          <label className="row" style={{ gap: 6 }}>
            <span className="muted">{d.status}</span>
            <select className="input" value={status} onChange={(e) => setStatus(e.target.value)}>
              <option value="">{d.all}</option>
              {STATUSES.map((s) => <option key={s} value={s}>{d.statuses[s]}</option>)}
            </select>
          </label>
          <label className="row" style={{ gap: 6 }}>
            <span className="muted">{d.project}</span>
            <input className="input" value={subject} placeholder="PROJ-31" onChange={(e) => setSubject(e.target.value)}
              onBlur={load} />
          </label>
        </form>
      </Card>
      {rows && rows.length === 0 && <Card><p className="muted" style={{ margin: 0 }}>{d.none}</p></Card>}
      {rows && rows.length > 0 && (
        <div className="reports-layout">
          <Card flush>
            <ul className="report-list" aria-label={t.nav.decisions}>
              {rows.map((x) => (
                <li key={x.id}>
                  <button className={x.id === picked ? "on" : ""} aria-current={x.id === picked} onClick={() => setPicked(x.id)}>
                    <span className="row" style={{ gap: 6, justifyContent: "space-between" }}>
                      <b>{d.kinds[x.kind] ?? x.kind}</b>
                      <span className={`badge ${TONE[x.status] ?? ""}`}>{d.statuses[x.status] ?? x.status}</span>
                    </span>
                    <span>{x.title}</span>
                    <span className="muted small"><code>{x.id}</code> · {when(x.updated_at, lang)}</span>
                  </button>
                </li>
              ))}
            </ul>
          </Card>
          {rec ? (
            <Card title={rec.title} desc={<>
              <span className={`badge ${TONE[rec.status] ?? ""}`}>{d.statuses[rec.status] ?? rec.status}</span>{" "}
              {d.kinds[rec.kind] ?? rec.kind} · <code>{rec.subject}</code> · {when(rec.updated_at, lang)}
            </>} actions={
              <button className="ghost tip" data-tip={d.provTip} onClick={downloadProv}><Icon.download /> {d.prov}</button>
            }>
              <dl className="dlog">
                {rec.context && <><dt>{d.context}</dt><dd>{rec.context}</dd></>}
                <dt>{d.drivers}</dt>
                <dd>{rec.drivers.length === 0 ? <span className="muted">–</span> : (
                  <ul className="dlog-list">{rec.drivers.map((e, i) => <li key={i}>{t.rv.ev(e)}</li>)}</ul>
                )}</dd>
                <dt>{d.options}</dt>
                <dd>{rec.options.length === 0 ? <span className="muted">–</span> : (
                  <ul className="dlog-list">{rec.options.map((o, i) => (
                    <li key={i}>{o.option === "as proposed" ? d.asProposed : o.option === "alternative" ? d.alternative : o.option}
                      {o.message_id && <> · <code>{o.message_id.slice(0, 8)}</code></>}</li>
                  ))}</ul>
                )}</dd>
                <dt>{d.outcome}</dt>
                <dd>
                  {rec.outcome.chosen ? <><b>{d.chosen}:</b> {rec.outcome.chosen}</> : (d.statuses[rec.status] ?? rec.status)}
                  <div>{rec.outcome.justification ? <><b>{d.because}:</b> {rec.outcome.justification}</>
                    : <span className="muted">{d.noReason}</span>}</div>
                </dd>
                <dt>{d.consequences}</dt>
                <dd>{rec.consequences.length === 0 ? <span className="muted">–</span> : (
                  <ul className="dlog-list">{rec.consequences.map((c, i) => <li key={i}>{c}</li>)}</ul>
                )}</dd>
                <dt>{d.makers}</dt><dd>{people(rec.decision_makers)}</dd>
                <dt>{d.consulted}</dt><dd>{people(rec.consulted)}</dd>
                <dt>{d.informed}</dt>
                <dd>{rec.informed.length === 0 ? <span className="muted">{d.nobodyTold}</span> : (
                  <ul className="dlog-list">{rec.informed.map((i, n) => i.who ? (
                    <li key={n}><b>{i.who}</b> <span className="muted">{t.rv.role[i.role ?? ""] ?? i.role}</span></li>
                  ) : (
                    <li key={n}><code>{i.event}</code> → <b>{i.channel}</b>{" "}
                      <span className={`badge ${SENT[i.status ?? ""] ?? ""}`}>{d[i.status as "sent" | "failed" | "skipped"] ?? i.status}</span>
                      {i.error && <span className="muted"> {i.error}</span>}</li>
                  ))}</ul>
                )}</dd>
                {(rec.supersedes || rec.run_id || rec.message_id) && <>
                  <dt>{d.run}</dt>
                  <dd className="row" style={{ gap: 12, flexWrap: "wrap" }}>
                    {rec.run_id && <code title={rec.run_id}>{rec.run_id.slice(0, 12)}</code>}
                    {rec.message_id && <span>{d.message} <code>{rec.message_id.slice(0, 8)}</code></span>}
                    {rec.supersedes && <button className="ghost sm" onClick={() => setPicked(rec.supersedes!)}>{d.supersedes} {rec.supersedes}</button>}
                  </dd>
                </>}
              </dl>
              <h3 className="dlog-sub">{t.timeline.title}</h3>
              {owed.length === 0 ? <p className="muted">{t.timeline.none}</p> : owed.map((c) => (
                <div key={c.id} className="dlog-owed">
                  <div className="row" style={{ gap: 6, flexWrap: "wrap" }}>
                    <b>{c.consequent}</b>
                    <span className="badge">{t.inbox.states[c.state] ?? c.state}</span>
                    <span className="muted">{t.inbox.owes(c.debtor, c.creditor)}{c.due ? ` · ${t.inbox.due} ${c.due.slice(0, 10)}` : ""}</span>
                  </div>
                  <ol className="timeline">
                    {c.history.map((h, i) => (
                      <li key={i} className={`tl-${h.op}`}>
                        <b>{t.timeline.ops[h.op] ?? h.op}</b> <span className="muted">{h.by} · {when(h.at, lang)}</span>
                        {h.note && <div className="muted small">{h.note}</div>}
                      </li>
                    ))}
                  </ol>
                </div>
              ))}
            </Card>
          ) : <Card><p className="muted">{d.pick}</p></Card>}
        </div>
      )}
    </div>
  );
}
