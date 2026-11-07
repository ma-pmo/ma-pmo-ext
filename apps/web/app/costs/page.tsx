"use client";
// The cost ledger: what LLM calls cost, from a versioned price table. A call whose model has no
// known price is counted separately and never folded into the USD total.
import { useEffect, useState } from "react";
import { api, problemsOf } from "../lib/api";
import { useI18n } from "../lib/i18n";
import { Card, PageHeader, Stat } from "../components/shell";
import { Icon } from "../components/icons";

type Row = {
  key: string | null; calls: number; prompt_tokens: number; completion_tokens: number;
  cache_read_tokens: number; usd: number | null; unpriced: number;
};
type Summary = { by: string; price_table: string; total: Row; rows: Row[] };
type Limits = { warn_usd: number | null; limit_usd: number | null; updated_by: string | null };
type Budgets = { period: string; month: Limits & { spent_usd: number }; run: Limits };
type FellBack = { run_id: string; workflow: string; started_at: string;
  budget_fallback: { kind: string; agent: string; step: number | null; limit_usd: number } | null };

const amount = (text: string) => (text.trim() === "" ? null : Number(text));

const GROUPS = ["model", "agent", "workflow", "day", "run"] as const;
const RANGES = [7, 30, 90, 0];

const money = (v: number | null | undefined, none = "–") =>
  v == null ? none : v === 0 ? "$0" : v < 0.01 ? `$${v.toFixed(4)}` : `$${v.toFixed(2)}`;
const num = (v: number) => v.toLocaleString();

export default function Costs() {
  const { lang, t } = useI18n();
  const c = t.cost;
  const [days, setDays] = useState(30);
  const [data, setData] = useState<Record<string, Summary>>({});
  const [err, setErr] = useState("");
  const [budget, setBudget] = useState<Budgets | null>(null);
  const [form, setForm] = useState({ mWarn: "", mLimit: "", rWarn: "", rLimit: "" });
  const [saving, setSaving] = useState(false);
  const [note, setNote] = useState<{ text: string; bad?: boolean } | null>(null);
  const [fellBack, setFellBack] = useState<FellBack[]>([]);

  const show = (b: Budgets) => {
    setBudget(b);
    const s = (v: number | null) => (v == null ? "" : String(v));
    setForm({ mWarn: s(b.month.warn_usd), mLimit: s(b.month.limit_usd), rWarn: s(b.run.warn_usd), rLimit: s(b.run.limit_usd) });
  };
  useEffect(() => {
    api.budgets().then(show).catch(() => {});
    api.runs({ limit: 200 }).then((rs: FellBack[]) => setFellBack(rs.filter((r) => r.budget_fallback))).catch(() => {});
  }, [lang]);

  const save = async () => {
    setSaving(true); setNote(null);
    try {
      await api.setBudget("month", amount(form.mWarn), amount(form.mLimit));
      show(await api.setBudget("run", amount(form.rWarn), amount(form.rLimit)));
      setNote({ text: c.saved });
    } catch (e) { setNote({ text: problemsOf(e).join(" · "), bad: true }); } finally { setSaving(false); }
  };

  useEffect(() => {
    Promise.all(GROUPS.map((g) => api.costs(g, days || undefined)))
      .then((all: Summary[]) => { setData(Object.fromEntries(all.map((s) => [s.by, s]))); setErr(""); })
      .catch((e) => setErr(String(e.message || e)));
  }, [days, lang]);

  const total = data.model?.total;
  const table = (g: string) => {
    const rows = data[g]?.rows ?? [];
    const top = Math.max(0, ...rows.map((r) => r.usd ?? 0));
    const shown = g === "day" ? [...rows].sort((a, b) => String(b.key).localeCompare(String(a.key))) : rows;
    return (
      <Card key={g} title={c.by[g]} flush>
        <div className="table-wrap">
          <table className="cost-table">
            <thead><tr><th>{c.key}</th><th>{c.calls}</th><th>{c.tokens}</th><th>{c.usd}</th><th aria-hidden="true" /></tr></thead>
            <tbody>
              {shown.slice(0, g === "run" ? 15 : 31).map((r) => (
                <tr key={String(r.key)}>
                  <td>{g === "run" || g === "model" ? <code>{r.key ?? "–"}</code> : (r.key ?? "–")}</td>
                  <td>{num(r.calls)}</td>
                  <td>{num(r.prompt_tokens)} / {num(r.completion_tokens)}</td>
                  <td>
                    {money(r.usd, c.noPrice)}
                    {r.unpriced > 0 && r.usd != null && (
                      <span className="badge amber tip" data-tip={c.unpricedTip} style={{ marginLeft: 6 }}>{c.plusUnpriced(r.unpriced)}</span>
                    )}
                  </td>
                  <td aria-hidden="true">
                    {r.usd != null && top > 0 && <span className="cost-bar"><i style={{ width: `${Math.max(2, (r.usd / top) * 100)}%` }} /></span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    );
  };

  return (
    <div className="stack">
      <PageHeader title={t.nav.costs} desc={t.pages.costs} actions={
        <label className="row" style={{ gap: 6 }}>
          <span className="muted">{c.range}</span>
          <select className="input" value={days} onChange={(e) => setDays(Number(e.target.value))}>
            {RANGES.map((d) => <option key={d} value={d}>{d ? c.days(d) : c.all}</option>)}
          </select>
        </label>
      } />
      {err && <div className="card" style={{ color: "var(--red)" }}>{t.common.error}: {err}</div>}
      {total && (
        <div className="grid cols-4">
          <Stat icon={<Icon.coins />} label={c.usd} value={money(total.usd, "$0")} sub={c.table(data.model.price_table)} />
          <Stat icon={<Icon.trend />} label={c.calls} value={num(total.calls)} />
          <Stat icon={<Icon.clock />} label={c.tokens} value={`${num(total.prompt_tokens)} / ${num(total.completion_tokens)}`}
            sub={`${c.cached}: ${num(total.cache_read_tokens)}`} />
          <Stat icon={<Icon.alert />} label={c.unpriced} value={num(total.unpriced)} tip={c.unpricedTip} />
        </div>
      )}
      {budget && (
        <Card title={c.budgets} desc={c.budgetsDesc}>
          <div className="grid cols-2">
            <div>
              <b>{c.month(budget.period)}</b>
              <div className="budget-bar" aria-hidden="true">
                {budget.month.limit_usd ? (
                  <>
                    <i style={{ width: `${Math.min(100, (budget.month.spent_usd / budget.month.limit_usd) * 100)}%` }}
                      className={budget.month.spent_usd >= budget.month.limit_usd ? "over"
                        : budget.month.warn_usd != null && budget.month.spent_usd >= budget.month.warn_usd ? "warn" : ""} />
                    {budget.month.warn_usd != null && (
                      <s style={{ left: `${Math.min(100, (budget.month.warn_usd / budget.month.limit_usd) * 100)}%` }} />
                    )}
                  </>
                ) : null}
              </div>
              <p className="muted" style={{ margin: "4px 0 10px" }}>
                {budget.month.limit_usd ? c.spentOf(money(budget.month.spent_usd, "$0"), money(budget.month.limit_usd))
                  : `${money(budget.month.spent_usd, "$0")} · ${c.noLimit}`}
              </p>
              <div className="row budget-form">
                <label><span>{c.warn}</span><input className="input" inputMode="decimal" value={form.mWarn} placeholder={c.notSet} aria-label={`${c.month(budget.period)} · ${c.warn}`}
                  onChange={(e) => setForm({ ...form, mWarn: e.target.value })} /></label>
                <label><span>{c.limit}</span><input className="input" inputMode="decimal" value={form.mLimit} placeholder={c.notSet} aria-label={`${c.month(budget.period)} · ${c.limit}`}
                  onChange={(e) => setForm({ ...form, mLimit: e.target.value })} /></label>
              </div>
            </div>
            <div>
              <b>{c.perRun}</b>
              <p className="muted" style={{ margin: "4px 0 10px" }}>
                {budget.run.limit_usd != null ? money(budget.run.limit_usd) : c.noLimit}
              </p>
              <div className="row budget-form">
                <label><span>{c.warn}</span><input className="input" inputMode="decimal" value={form.rWarn} placeholder={c.notSet} aria-label={`${c.perRun} · ${c.warn}`}
                  onChange={(e) => setForm({ ...form, rWarn: e.target.value })} /></label>
                <label><span>{c.limit}</span><input className="input" inputMode="decimal" value={form.rLimit} placeholder={c.notSet} aria-label={`${c.perRun} · ${c.limit}`}
                  onChange={(e) => setForm({ ...form, rLimit: e.target.value })} /></label>
              </div>
            </div>
          </div>
          <div className="row" style={{ marginTop: 12 }}>
            <button onClick={save} disabled={saving}>{saving ? c.saving : c.save}</button>
            {note && <span role="status" className={`badge ${note.bad ? "red" : "green"}`} style={{ whiteSpace: "normal" }}>{note.text}</span>}
          </div>
        </Card>
      )}
      {fellBack.length > 0 && (
        <Card title={c.fellBack} flush>
          <div className="table-wrap">
            <table className="cost-table">
              <tbody>
                {fellBack.slice(0, 20).map((r) => (
                  <tr key={r.run_id}>
                    <td>{new Date(r.started_at).toLocaleString()}</td>
                    <td><a href={`/workflows?id=${encodeURIComponent(r.workflow)}&run=${encodeURIComponent(r.run_id)}`}>{r.workflow}</a></td>
                    <td style={{ whiteSpace: "normal" }}>{c.fellBackRow(r.budget_fallback!.kind, r.budget_fallback!.agent, r.budget_fallback!.step)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
      {total && total.calls === 0 && <Card><p className="muted" style={{ margin: 0 }}>{c.none}</p></Card>}
      {total && total.calls > 0 && (
        <div className="grid cols-2">{GROUPS.map(table)}</div>
      )}
    </div>
  );
}
