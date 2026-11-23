"use client";
// The inbox (roadmap 9): questions agents asked people, and what decisions oblige people to do.
// Answer a question, mark a commitment done with a reference, hand it over, or release it.
// GET /questions, GET /commitments; see docs/REVIEW.md (Questions, Commitments).
import { useEffect, useState } from "react";
import { api, errorText } from "../lib/api";
import { useI18n } from "../lib/i18n";
import { when } from "../lib/time";
import { Card, PageHeader, ErrorCard } from "../components/shell";
import { Icon } from "../components/icons";

type Com = {
  id: string; kind: string; debtor: string; creditor: string; consequent: string; due: string | null;
  state: string; project_id: string | null; escalation: number; source_decision: string | null;
  check: { answer_type?: string; options?: string[]; default?: unknown; why?: string } | null;
};

const OPEN = ["conditional", "active", "violated"];
const TONE: Record<string, string> = { active: "accent", conditional: "", violated: "red", satisfied: "green",
  expired: "", cancelled: "", released: "" };
const ME_KEY = "ma-pmo.inbox.me";

export default function Inbox() {
  const { lang, t } = useI18n();
  const x = t.inbox;
  const [rows, setRows] = useState<Com[] | null>(null);
  const [me, setMe] = useState("");
  const [closed, setClosed] = useState(false);
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [err, setErr] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState("");

  useEffect(() => { try { setMe(localStorage.getItem(ME_KEY) || ""); } catch { /* private mode */ } }, []);
  const remember = (v: string) => { setMe(v); try { localStorage.setItem(ME_KEY, v); } catch { /* ignore */ } };

  const load = async () => {
    try { setRows(await api.commitments()); setErr(""); } catch (e) { setErr(errorText(e)); }
  };
  useEffect(() => { load(); }, [lang]);  // eslint-disable-line react-hooks/exhaustive-deps

  const actor = me.trim() || "anonymous";
  const act = async (id: string, run: () => Promise<unknown>) => {
    setBusy(id); setErr(""); setNote("");
    try { await run(); setNote(x.saved); setDraft((d) => ({ ...d, [id]: "", [`${id}:to`]: "" })); await load(); }
    catch (e) { setErr(errorText(e)); } finally { setBusy(""); }
  };

  const mine = (c: Com) => !me.trim() || c.debtor.split(", ").includes(me.trim()) || c.creditor === me.trim();
  const visible = (rows ?? []).filter((c) => mine(c) && (closed || OPEN.includes(c.state)));
  const questions = visible.filter((c) => c.kind === "question");
  const owed = visible.filter((c) => c.kind !== "question");
  // the server decides what is overdue, on the project calendar (MA_PMO_REPORT_AS_OF), not today
  const overdue = (c: Com) => c.state === "violated";

  const dueLine = (c: Com) => c.due && (
    <span className={overdue(c) ? "badge red" : "muted"}>{overdue(c) ? x.overdue : x.due} {c.due.slice(0, 10)}</span>
  );

  const answerField = (c: Com) => {
    const id = `ans-${c.id}`, value = draft[c.id] ?? "", set = (v: string) => setDraft((d) => ({ ...d, [c.id]: v }));
    const kind = c.check?.answer_type;
    if (kind === "date") return <input id={id} className="input" type="date" value={value} onChange={(e) => set(e.target.value)} />;
    if (kind === "yes_no" || kind === "choice") {
      const opts = kind === "yes_no" ? [["yes", x.yes], ["no", x.no]] : (c.check?.options ?? []).map((o) => [o, o]);
      return (
        <select id={id} className="input" value={value} onChange={(e) => set(e.target.value)}>
          <option value="">{x.pick}</option>
          {opts.map(([v, label]) => <option key={v} value={v}>{label}</option>)}
        </select>
      );
    }
    return <input id={id} className="input" value={value} onChange={(e) => set(e.target.value)} />;
  };

  return (
    <div className="stack">
      <PageHeader title={t.nav.inbox} desc={t.pages.inbox}
        actions={<button className="ghost" onClick={load}><Icon.refresh />{t.common2.refresh}</button>} />
      {err && <ErrorCard label={t.common.error}>{err}</ErrorCard>}
      <Card>
        <div className="row" style={{ gap: 12, flexWrap: "wrap" }}>
          <label className="row" style={{ gap: 6 }}>
            <span className="muted">{x.me}</span>
            <input className="input" value={me} placeholder={x.mePlaceholder} onChange={(e) => remember(e.target.value)} />
          </label>
          <label className="row" style={{ gap: 6 }}>
            <input type="checkbox" checked={closed} onChange={(e) => setClosed(e.target.checked)} />
            <span>{x.showClosed}</span>
          </label>
          {note && <span role="status" className="badge green">{note}</span>}
        </div>
      </Card>

      <Card title={x.questions} flush>
        {rows && questions.length === 0 ? <div className="empty">{x.noQuestions}</div> : (
          <ul className="inbox-list">
            {questions.map((c) => (
              <li key={c.id}>
                <div className="row" style={{ gap: 8, justifyContent: "space-between", flexWrap: "wrap" }}>
                  <b>{c.consequent}</b>
                  <span className="row" style={{ gap: 6 }}>
                    <span className={`badge ${TONE[c.state] ?? ""}`}>{x.states[c.state] ?? c.state}</span>{dueLine(c)}
                  </span>
                </div>
                <div className="muted">{x.asked(c.creditor, c.debtor)}{c.check?.why ? ` · ${x.why}: ${c.check.why}` : ""}</div>
                <div className="muted small">{x.ifNot(String(c.check?.default ?? "—"))}</div>
                {OPEN.slice(0, 2).includes(c.state) && (
                  <form className="row inbox-actions" onSubmit={(e) => {
                    e.preventDefault();
                    act(c.id, () => api.answerQuestion(c.id, actor, draft[c.id]));
                  }}>
                    <label htmlFor={`ans-${c.id}`} className="sr-only">{x.answer}</label>
                    {answerField(c)}
                    <button className="sm" disabled={busy === c.id || !(draft[c.id] ?? "").trim()}>{x.answer}</button>
                  </form>
                )}
              </li>
            ))}
          </ul>
        )}
      </Card>

      <Card title={x.commitments} flush>
        {rows && owed.length === 0 ? <div className="empty">{x.noCommitments}</div> : (
          <ul className="inbox-list">
            {owed.map((c) => (
              <li key={c.id}>
                <div className="row" style={{ gap: 8, justifyContent: "space-between", flexWrap: "wrap" }}>
                  <b>{c.consequent}</b>
                  <span className="row" style={{ gap: 6, flexWrap: "wrap" }}>
                    <span className="badge">{x.kinds[c.kind] ?? c.kind}</span>
                    <span className={`badge ${TONE[c.state] ?? ""}`}>{x.states[c.state] ?? c.state}</span>
                    {dueLine(c)}
                    {c.escalation > 0 && <span className="badge amber">{x.escalation(c.escalation)}</span>}
                  </span>
                </div>
                <div className="muted">
                  {x.owes(c.debtor, c.creditor)}{c.project_id ? ` · ${c.project_id}` : ""}
                  {c.source_decision && <> · <a href={`/decisions?id=${encodeURIComponent(c.source_decision)}`}>{c.source_decision}</a></>}
                </div>
                {OPEN.includes(c.state) && (
                  <div className="row inbox-actions">
                    {c.state !== "violated" && <>
                      <label htmlFor={`ref-${c.id}`} className="sr-only">{x.reference}</label>
                      <input id={`ref-${c.id}`} className="input" placeholder={x.reference} value={draft[c.id] ?? ""}
                        onChange={(e) => setDraft((d) => ({ ...d, [c.id]: e.target.value }))} />
                      <button className="sm" disabled={busy === c.id}
                        onClick={() => act(c.id, () => api.commitmentOp(c.id, "discharge",
                          { by: actor, reference: (draft[c.id] ?? "").trim() || undefined }))}>{x.done}</button>
                      <label htmlFor={`to-${c.id}`} className="sr-only">{x.handTo}</label>
                      <input id={`to-${c.id}`} className="input" placeholder={x.handTo} value={draft[`${c.id}:to`] ?? ""}
                        onChange={(e) => setDraft((d) => ({ ...d, [`${c.id}:to`]: e.target.value }))} />
                      <button className="sm ghost" disabled={busy === c.id || !(draft[`${c.id}:to`] ?? "").trim()}
                        onClick={() => act(c.id, () => api.commitmentOp(c.id, "delegate",
                          { by: actor, to: draft[`${c.id}:to`] }))}>{x.delegate}</button>
                    </>}
                    <button className="sm ghost" disabled={busy === c.id}
                      onClick={() => act(c.id, () => api.commitmentOp(c.id, "release", { by: actor }))}>{x.release}</button>
                  </div>
                )}
                <div className="muted small"><code>{c.id}</code>{c.due ? ` · ${when(c.due, lang)}` : ""}</div>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
