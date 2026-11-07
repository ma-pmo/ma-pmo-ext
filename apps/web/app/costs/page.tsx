"use client";
// The cost ledger: what LLM calls cost, from a versioned price table. A call whose model has no
// known price is counted separately and never folded into the USD total.
import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { useI18n } from "../lib/i18n";
import { Card, PageHeader, Stat } from "../components/shell";
import { Icon } from "../components/icons";

type Row = {
  key: string | null; calls: number; prompt_tokens: number; completion_tokens: number;
  cache_read_tokens: number; usd: number | null; unpriced: number;
};
type Summary = { by: string; price_table: string; total: Row; rows: Row[] };

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
      {total && total.calls === 0 && <Card><p className="muted" style={{ margin: 0 }}>{c.none}</p></Card>}
      {total && total.calls > 0 && (
        <div className="grid cols-2">{GROUPS.map(table)}</div>
      )}
    </div>
  );
}
