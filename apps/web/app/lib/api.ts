// FastAPI backend client. Every request carries the UI language (?lang=en|ko) and, once one
// is picked, the workspace (X-Workspace).
const BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";
// Only when the API runs with MA_PMO_AUTH_MODE=api_key. The key is visible to anyone who can
// open the dashboard, so use a viewer/approver key and keep the dashboard on a private network.
const API_KEY = process.env.NEXT_PUBLIC_API_KEY || "";

let LANG = "en";
export function setApiLang(lang: string) {
  LANG = lang;
}
let WORKSPACE = "";
export function setApiWorkspace(workspace: string) {
  WORKSPACE = workspace;
}
const scoped = (path: string, scope?: string) =>
  scope ? `${path}${path.includes("?") ? "&" : "?"}scope=${encodeURIComponent(scope)}` : path;

async function req(path: string, init?: RequestInit) {
  const sep = path.includes("?") ? "&" : "?";
  const headers = new Headers(init?.headers);
  if (API_KEY) headers.set("X-API-Key", API_KEY);
  if (WORKSPACE) headers.set("X-Workspace", WORKSPACE);
  const res = await fetch(`${BASE}${path}${sep}lang=${LANG}`, { cache: "no-store", ...init, headers });
  if (!res.ok) throw new Error(`${res.status} ${await res.text()}`);
  return res.json();
}

export const api = {
  portfolio: (id: string) => req(`/portfolio/${encodeURIComponent(id)}`),
  kpi: (axis?: string) => req(`/kpi${axis ? `?axis=${axis}` : ""}`),
  risks: (scope?: string) => req(scoped(`/risks`, scope)),
  allocations: (scope?: string) => req(scoped(`/allocations`, scope)),
  messages: (limit = 15) => req(`/messages?limit=${limit}`),
  plan: (scope?: string) => req(scoped(`/plan`, scope), { method: "POST" }),
  allocate: (scope?: string) => req(scoped(`/allocate`, scope), { method: "POST" }),
  scenarios: () => req(`/scenarios`),
  workflows: () => req(`/workflows`),
  workflow: (id: string) => req(`/workflows/${encodeURIComponent(id)}`),
  runScenario: (id: string) =>
    req(`/scenarios/${id}/run?format=markdown`, { method: "POST" }),
  gateReview: (gate = "G2-planning", scope?: string) =>
    req(scoped(`/gate-review?gate=${encodeURIComponent(gate)}`, scope), { method: "POST" }),
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
  health: () => req(`/health`),
  evaluation: () => req(`/eval`),
  retrieval: () => req(`/eval/retrieval`),
  system: () => req(`/system`),
  whoami: () => req(`/auth/whoami`),
  workspaces: () => req(`/workspaces`),
  portfolios: () => req(`/portfolios`),
  validateTemplate: (zip: Blob) =>
    req(`/templates/validate`, {
      method: "POST",
      headers: { "content-type": "application/zip" },
      body: zip,
    }),
  integrations: () => req(`/integrations`),
  testIntegration: (name: string) =>
    req(`/integrations/${encodeURIComponent(name)}/test`, { method: "POST" }),
};

// direct links (downloads, reports opened in a new tab)
export const links = {
  reportHtml: () => `${BASE}/eval/report?format=html&lang=${LANG}`,
  reportMd: () => `${BASE}/eval/report?format=md&lang=${LANG}`,
  dataTemplate: (empty = false) => `${BASE}/templates/data.zip${empty ? "?empty=true" : ""}`,
};
