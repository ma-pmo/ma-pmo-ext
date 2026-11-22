"use client";
// One run's conversation and notifications (roadmap 8): each decision with the reviews that
// answer it (in_reply_to), and every notification attempt (GET /communications?run=).
import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { useI18n } from "../lib/i18n";
import { clock } from "../lib/time";
import { Card } from "../components/shell";

type Msg = { message_id: string; sender: string; receiver: string; schema: string; timestamp: string; task_ref: string;
  in_reply_to: string | null; payload?: { data?: Record<string, any> } };
type Comm = { id: number; event: string; channel: string; status: string; error: string | null;
  created_at: string };

const VERDICT: Record<string, string> = { VERIFIED: "green", CHALLENGE: "red", ALTERNATIVE: "accent" };
const SENT: Record<string, string> = { sent: "green", failed: "red", skipped: "" };

export function ThreadCard({ runId }: { runId: string }) {
  const { lang, t } = useI18n();
  const th = t.thread;
  const [msgs, setMsgs] = useState<Msg[] | null>(null);
  const [comms, setComms] = useState<Comm[]>([]);

  useEffect(() => {
    let alive = true;
    api.conversation(runId).then((m: Msg[]) => alive && setMsgs(m)).catch(() => alive && setMsgs([]));
    api.communications(runId).then((c: Comm[]) => alive && setComms(c)).catch(() => {});
    return () => { alive = false; };
  }, [runId, lang]);

  if (msgs === null) return null;
  const ordered = [...msgs].sort((a, b) => a.timestamp.localeCompare(b.timestamp));
  const replies: Record<string, Msg[]> = {};
  for (const m of ordered) if (m.in_reply_to) (replies[m.in_reply_to] ??= []).push(m);
  const roots = ordered.filter((m) => !m.in_reply_to || !ordered.some((o) => o.message_id === m.in_reply_to));
  const notes = [...comms].reverse();

  return (
    <Card title={th.title} desc={th.desc} flush>
      {roots.length === 0 ? <div className="empty">{th.none}</div> : (
        <div className="table-wrap">
          <table className="wf-table">
            <tbody>
              {roots.map((m) => (
                <tr key={m.message_id}>
                  <td className="muted" style={{ whiteSpace: "nowrap" }}>{clock(m.timestamp, lang)}</td>
                  <td><span className="badge accent">{m.sender}→{m.receiver}</span></td>
                  <td>
                    <code>{m.schema}</code>
                    {m.task_ref.includes("/") && <span className="muted"> · {m.task_ref.split("/").pop()}</span>}
                    {replies[m.message_id] && (
                      <ul className="thread-replies" aria-label={th.replies(replies[m.message_id].length)}>
                        {replies[m.message_id].map((r) => {
                          const v = r.payload?.data?.verdict as string | undefined;
                          return (
                            <li key={r.message_id}>
                              {r.sender} · {v ? <span className={`badge ${VERDICT[v] ?? ""}`}>{v}</span> : <code>{r.schema}</code>}
                              {r.payload?.data?.constraint && <span className="muted"> {t.rv.constraint[r.payload.data.constraint] ?? r.payload.data.constraint}</span>}
                            </li>
                          );
                        })}
                      </ul>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <div style={{ padding: "12px 16px 0" }}><b>{th.notifications}</b></div>
      {notes.length === 0 ? <div className="empty">{th.noNotifications}</div> : (
        <div className="table-wrap">
          <table className="wf-table">
            <thead><tr><th>{t.common.time}</th><th>{th.event}</th><th>{th.channel}</th><th>{th.status}</th><th>{th.why}</th></tr></thead>
            <tbody>
              {notes.map((c) => (
                <tr key={c.id}>
                  <td className="muted" style={{ whiteSpace: "nowrap" }}>{clock(c.created_at, lang)}</td>
                  <td><code>{c.event}</code></td>
                  <td>{c.channel}</td>
                  <td><span className={`badge ${SENT[c.status] ?? ""}`}>{t.dlog[c.status as "sent" | "failed" | "skipped"] ?? c.status}</span></td>
                  <td className="muted">{c.error ?? ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}
