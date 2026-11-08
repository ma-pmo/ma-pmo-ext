"use client";
// The board of one run: what each step published, what it was allowed to read, the verdicts it
// posted, and what the run committed (GET /runs/{id}/board). See docs/REVIEW.md.
import { useI18n } from "../lib/i18n";
import { Card } from "../components/shell";

type Post = { message_id: string; step: string; agent: string; schema: string; data: Record<string, any> };
type Decision = { message_id: string; schema: string; step: string; project_id?: string | null; status: string;
  challenges: string[]; missing: string[] };
export type Board = {
  review: boolean;
  steps: { id: string; agent: string; reads: string; can_read: string[] }[];
  posts: Post[];
  commit: Decision[] | null;
};

export function BoardCard({ board }: { board: Board }) {
  const { t } = useI18n();
  const r = t.rv;
  const verdicts = (step: string) => {
    const n: Record<string, number> = {};
    for (const p of board.posts) {
      if (p.step === step && p.schema === "review.v1") n[p.data.verdict] = (n[p.data.verdict] ?? 0) + 1;
    }
    return n;
  };
  const posted = (step: string) => board.posts.filter((p) => p.step === step && p.schema !== "review.v1").length;
  return (
    <Card title={r.board} desc={r.boardDesc} flush>
      {board.commit && board.commit.length > 0 && (
        <div className="wf-runbar" style={{ padding: "0 16px 12px", flexWrap: "wrap" }}>
          <span className="muted">{r.decisions}</span>
          {board.commit.map((d) => (
            <a key={d.message_id} href={d.status === "review_pending" ? "/approvals" : undefined}
              className={`badge ${d.status === "committed" ? "green" : "amber"}`}>
              {d.project_id ?? d.schema.replace(".v1", "")} · {r.status[d.status] ?? d.status}
            </a>
          ))}
        </div>
      )}
      <div className="table-wrap">
        <table className="wf-table">
          <thead>
            <tr><th>{t.wf.step}</th><th>{t.wf.agent}</th><th><span className="tip" data-tip={r.readsTip}>{r.reads}</span></th>
              <th>{r.canRead}</th><th className="num">{r.posts}</th><th>{r.verdicts}</th></tr>
          </thead>
          <tbody>
            {board.steps.map((s) => {
              const v = verdicts(s.id);
              return (
                <tr key={s.id}>
                  <td><code>{s.id}</code></td>
                  <td>{s.agent}</td>
                  <td>{s.reads === "isolated" ? <span className="muted">{r.readsNames.isolated}</span> : <span className="badge accent">{r.readsNames[s.reads] ?? s.reads}</span>}</td>
                  <td>{s.can_read.length ? s.can_read.join(", ") : <span className="muted">–</span>}</td>
                  <td className="num">{posted(s.id)}</td>
                  <td>
                    {Object.keys(v).length === 0 ? <span className="muted">–</span> : (
                      <div className="row" style={{ gap: 4 }}>
                        {v.VERIFIED ? <span className="badge green">VERIFIED {v.VERIFIED}</span> : null}
                        {v.CHALLENGE ? <span className="badge red">CHALLENGE {v.CHALLENGE}</span> : null}
                        {v.ALTERNATIVE ? <span className="badge accent">ALTERNATIVE {v.ALTERNATIVE}</span> : null}
                      </div>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </Card>
  );
}
