"use client";
import { useEffect, useState } from "react";
import { api, links } from "../lib/api";
import { useI18n } from "../lib/i18n";
import { Card, PageHeader } from "../components/shell";
import { Icon } from "../components/icons";

const VERDICT_CLASS: Record<string, string> = {
  supported: "green", partial: "amber", not_supported: "red", insufficient: "",
};

export default function Evaluation() {
  const { lang, t } = useI18n();
  const e = t.evalp;
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState("");
  const [check, setCheck] = useState<any>(null);
  const [checking, setChecking] = useState(false);

  async function load() {
    setLoading(true); setErr("");
    try { setData(await api.evaluation()); }
    catch (x: any) { setErr(String(x.message || x)); }
    finally { setLoading(false); }
  }
  useEffect(() => { load(); setCheck(null); }, [lang]);

  async function onFile(file: File | undefined) {
    if (!file) return;
    setChecking(true); setCheck(null); setErr("");
    try { setCheck(await api.validateTemplate(file)); }
    catch (x: any) { setErr(String(x.message || x)); }
    finally { setChecking(false); }
  }

  const verdictLabel = (v: string) => (e as any)[`verdict_${v}`] ?? v;
  const errors = check ? check.issues.filter((i: any) => i.level === "error").length : 0;

  return (
    <div className="stack">
      <PageHeader
        title={t.nav.evaluation}
        desc={t.pages.evaluation}
        actions={<>
          <button className="ghost" onClick={load} disabled={loading}><Icon.refresh />{t.common2.refresh}</button>
          <a className="btn" href={links.reportHtml()} target="_blank" rel="noreferrer"><Icon.external />{e.openHtml}</a>
        </>}
      />
      {err && <div className="card" style={{ color: "var(--red)" }}>{t.common.apiError}: {err}</div>}

      <Card flush title={e.verdicts} desc={e.verdictsDesc}>
        {!data ? <div className="empty">{t.common2.loading}</div> : (
          <div className="table-wrap">
            <table>
              <thead><tr><th>{e.hyp}</th><th>{e.claim}</th><th>{e.evidence}</th><th>{e.verdict}</th></tr></thead>
              <tbody>
                {data.summary.map((r: any) => (
                  <tr key={r.id}>
                    <td><b>{r.id}</b></td>
                    <td>{r.claim}</td>
                    <td className="muted">{r.evidence}</td>
                    <td><span className={`badge ${VERDICT_CLASS[r.verdict] ?? ""}`}>{verdictLabel(r.verdict)}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <div className="grid cols-3">
        <Card title={e.report} desc={e.reportDesc}>
          <div className="row">
            <a className="btn" href={links.reportHtml()} target="_blank" rel="noreferrer"><Icon.external />{e.openHtml}</a>
            <a className="btn ghost" href={links.reportMd()}><Icon.download />{e.downloadMd}</a>
          </div>
          <pre className="code" style={{ marginTop: 12 }}>ma-pmo template report --format html --out report.html</pre>
        </Card>

        <Card title={e.template} desc={e.templateDesc}>
          <div className="row">
            <a className="btn" href={links.dataTemplate()}><Icon.download />{e.downloadTemplate}</a>
            <a className="btn ghost sm" href={links.dataTemplate(true)}>{e.downloadEmpty}</a>
          </div>
          <label className="muted" style={{ display: "block", margin: "14px 0 6px" }}>{e.validate}</label>
          <input className="input" type="file" accept=".zip,application/zip" style={{ width: "100%" }}
            onChange={(ev) => onFile(ev.target.files?.[0])} disabled={checking} />
          <div className="muted" style={{ marginTop: 6 }}>{e.validateHint}</div>
        </Card>

        <Card title={e.experiments} desc={e.experimentsDesc}>
          <pre className="code">{`ma-pmo harness new risk_focus \\
  --hypothesis H3 --repeat 3
ma-pmo harness risk_focus`}</pre>
        </Card>
      </div>

      {(checking || check) && (
        <Card flush
          title={checking ? t.common2.loading : check.valid ? e.valid : e.invalid(errors)}
          desc={check && e.counts(check.counts.projects, check.counts.tasks, check.counts.resources, check.counts.risk_labels)}
          actions={check && <span className={`badge ${check.valid ? "green" : "red"}`}>{check.scope || "–"}</span>}>
          {check && check.issues.length > 0 && (
            <div className="table-wrap">
              <table>
                <thead><tr><th>{e.level}</th><th>{e.file}</th><th className="num">{e.line}</th><th>{e.message}</th></tr></thead>
                <tbody>
                  {check.issues.map((i: any, k: number) => (
                    <tr key={k}>
                      <td><span className={`badge ${i.level === "error" ? "red" : "amber"}`}>{i.level}</span></td>
                      <td><code>{i.file}</code></td>
                      <td className="num">{i.line ?? "–"}</td>
                      <td>{i.message}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {check?.valid && (
            <div style={{ padding: "0 16px 16px" }}>
              <div className="muted" style={{ margin: "4px 0 6px" }}>{e.cli}</div>
              <pre className="code">{`ma-pmo eval --data ./ma-pmo-eval-data
ma-pmo template report --data ./ma-pmo-eval-data --format html --out report.html`}</pre>
            </div>
          )}
        </Card>
      )}
    </div>
  );
}
