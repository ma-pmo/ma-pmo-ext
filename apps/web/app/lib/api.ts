// FastAPI backend client. Every request carries the UI language (?lang=en|ko).
const BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

let LANG = "en";
export function setApiLang(lang: string) {
  LANG = lang;
}

async function req(path: string, init?: RequestInit) {
  const sep = path.includes("?") ? "&" : "?";
  const res = await fetch(`${BASE}${path}${sep}lang=${LANG}`, { cache: "no-store", ...init });
  if (!res.ok) throw new Error(`${res.status} ${await res.text()}`);
  return res.json();
}

export const api = {
  portfolio: (id: string) => req(`/portfolio/${encodeURIComponent(id)}`),
  kpi: (axis?: string) => req(`/kpi${axis ? `?axis=${axis}` : ""}`),
  risks: () => req(`/risks`),
  allocations: () => req(`/allocations`),
  messages: (limit = 15) => req(`/messages?limit=${limit}`),
  plan: () => req(`/plan`, { method: "POST" }),
  allocate: () => req(`/allocate`, { method: "POST" }),
  scenarios: () => req(`/scenarios`),
  runScenario: (id: string) =>
    req(`/scenarios/${id}/run?format=markdown`, { method: "POST" }),
  gateReview: (gate = "G2-planning") =>
    req(`/gate-review?gate=${encodeURIComponent(gate)}`, { method: "POST" }),
  knowledgeSearch: (q: string) => req(`/knowledge/search?q=${encodeURIComponent(q)}`),
  approvals: () => req(`/approvals`),
  resolveApproval: (id: number, approver: string, decision: "approve" | "reject") =>
    req(`/approvals/${id}`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ approver, decision }),
    }),
  orchestrate: (goal: string, task_ref = "PORTFOLIO#2026-Q1") =>
    req(`/orchestrate`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ goal, task_ref }),
    }),
};
