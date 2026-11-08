"use client";
// Why the commit gate held a decision: the challenges with their evidence, the alternatives
// offered, and what nobody could check (GET /approvals → item.review). See docs/REVIEW.md.
import { useI18n } from "../lib/i18n";

type Ev = { kind: string; ref: string; field?: string; agent?: string; schema?: string };
type Entry = { agent: string; constraint: string; role?: string; rationale?: string; evidence?: Ev[];
  alternative?: { kind: string; summary: string } };
export type Review = { kind: string; challenges: Entry[]; alternatives: Entry[]; missing: string[] };

export function ReviewDetail({ review }: { review: Review }) {
  const { t } = useI18n();
  const r = t.rv;
  const label = (c: string) => r.constraint[c] ?? c;
  const evidence = (list?: Ev[]) => (list?.length ? (
    <div className="rv-ev" aria-label={r.evidence}>
      {list.map((e, i) => <span key={i} className="chip">{r.ev(e)}</span>)}
    </div>
  ) : null);
  return (
    <div className="rv">
      {review.challenges.length > 0 && (
        <div>
          <b className="rv-head">{r.challenged}</b>
          <ul>
            {review.challenges.map((c, i) => (
              <li key={i}>
                <span className="badge red">{label(c.constraint)}</span>{" "}
                <span className="muted">{r.role[c.role ?? ""] ?? c.role} · {c.agent}</span>
                <div>{c.rationale}</div>
                {evidence(c.evidence)}
              </li>
            ))}
          </ul>
        </div>
      )}
      {review.alternatives.length > 0 && (
        <div>
          <b className="rv-head">{r.alternatives}</b>
          <ul>
            {review.alternatives.map((a, i) => (
              <li key={i}>
                <span className="badge accent">{r.altKinds[a.alternative?.kind ?? ""] ?? a.alternative?.kind}</span>{" "}
                {a.alternative?.summary}
                {evidence(a.evidence)}
              </li>
            ))}
          </ul>
        </div>
      )}
      {review.missing.length > 0 && (
        <div><b className="rv-head">{r.missing}</b>{" "}
          {review.missing.map((m) => <span key={m} className="badge amber" style={{ marginRight: 6 }}>{label(m)}</span>)}
        </div>
      )}
    </div>
  );
}
