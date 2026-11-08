"use client";
// Admin app shell: grouped sidebar navigation, top bar with API status and language switch.
import { usePathname } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";
import { api } from "../lib/api";
import { useI18n } from "../lib/i18n";
import { usePlace } from "../lib/place";
import type { Lang } from "../lib/messages";
import { Icon } from "./icons";

const LANGS: { code: Lang; label: string }[] = [
  { code: "en", label: "EN" },
  { code: "ko", label: "한국어" },
];

type Item = { href: string; key: "dashboard" | "scenarios" | "workflows" | "approvals" | "evaluation" | "costs" | "integrations"; icon: () => JSX.Element };
const GROUPS: { key: "overview" | "operations" | "insights" | "settings"; items: Item[] }[] = [
  { key: "overview", items: [{ href: "/", key: "dashboard", icon: Icon.dashboard }] },
  {
    key: "operations",
    items: [
      { href: "/scenarios", key: "scenarios", icon: Icon.scenarios },
      { href: "/workflows", key: "workflows", icon: Icon.workflows },
      { href: "/approvals", key: "approvals", icon: Icon.approvals },
    ],
  },
  {
    key: "insights",
    items: [
      { href: "/evaluation", key: "evaluation", icon: Icon.evaluation },
      { href: "/costs", key: "costs", icon: Icon.costs },
    ],
  },
  { key: "settings", items: [{ href: "/integrations", key: "integrations", icon: Icon.integrations }] },
];

export function Shell({ children }: { children: ReactNode }) {
  const { lang, setLang, t } = useI18n();
  const place = usePlace();
  const path = usePathname();
  const [open, setOpen] = useState(false);
  const [apiUp, setApiUp] = useState<boolean | null>(null);
  const [pending, setPending] = useState(0);
  const [me, setMe] = useState<{ subject: string; auth_enabled: boolean } | null>(null);

  useEffect(() => {
    let alive = true;
    const poll = async () => {
      try {
        await api.health();
        const items = await api.approvals();
        if (alive) { setApiUp(true); setPending(items.length); }
      } catch {
        if (alive) setApiUp(false);
      }
    };
    poll();
    api.whoami().then((w) => alive && setMe(w)).catch(() => {});
    const id = setInterval(poll, 15000);
    return () => { alive = false; clearInterval(id); };
  }, [path]);

  useEffect(() => setOpen(false), [path]);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const current = GROUPS.flatMap((g) => g.items).find((i) => i.href === path);

  return (
    <div className="app">
      {open && <div className="backdrop" onClick={() => setOpen(false)} aria-hidden="true" />}
      <aside className={`sidebar ${open ? "open" : ""}`} aria-label={t.shell.menu}>
        <a className="brand" href="/">
          <img src="/logo.png" alt="" />
          <span><b>MA-PMO</b><small>{t.shell.subtitle}</small></span>
        </a>
        {place.workspaces.length > 0 && (
          <div className="place">
            <label>
              <span>{t.shell.workspace}</span>
              <select value={place.workspace} onChange={(e) => place.setWorkspace(e.target.value)}>
                {place.workspaces.map((w) => <option key={w.id} value={w.id}>{w.name}</option>)}
              </select>
            </label>
            {place.portfolios.length > 0 && (
              <label>
                <span>{t.shell.portfolio}</span>
                <select value={place.portfolio} onChange={(e) => place.setPortfolio(e.target.value)}>
                  {place.portfolios.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
                </select>
              </label>
            )}
          </div>
        )}
        {GROUPS.map((g) => (
          <div className="nav-group" key={g.key}>
            <span>{t.nav.groups[g.key]}</span>
            {g.items.map((it) => (
              <a key={it.href} href={it.href} className={`nav-item ${path === it.href ? "active" : ""}`}
                aria-current={path === it.href ? "page" : undefined}>
                <it.icon />
                {t.nav[it.key]}
                {it.key === "approvals" && pending > 0 && <span className="count">{pending}</span>}
              </a>
            ))}
          </div>
        ))}
        <div className="sidebar-foot">
          <a href="https://github.com/ma-pmo/ma-pmo-ext" target="_blank" rel="noreferrer">{t.shell.github}</a>
          {" · "}
          <a href="https://pypi.org/project/ma-pmo/" target="_blank" rel="noreferrer">PyPI</a>
        </div>
      </aside>

      <div className="main">
        <header className="topbar">
          <button className="ghost sm menu-btn" onClick={() => setOpen((v) => !v)} aria-label={t.shell.menu}>
            <Icon.menu />
          </button>
          <span className="crumb">{current ? t.nav[current.key] : "MA-PMO"}</span>
          <span className="spacer" />
          {me && (me.auth_enabled
            ? <span className="badge accent">{me.subject}</span>
            : <span className="badge amber tip" data-tip={t.shell.authOffTip}>{t.shell.authOff}</span>)}
          <span className={`status ${apiUp === null ? "" : apiUp ? "up" : "down"}`}
            title={apiUp === false ? t.shell.apiDown : t.shell.apiUp}>
            <i /><span className="status-label">{apiUp === false ? t.shell.apiDown : t.shell.apiUp}</span>
          </span>
          <div className="row" role="group" aria-label={t.langLabel}>
            {LANGS.map((l) => (
              <button key={l.code} className={`sm ${lang === l.code ? "" : "ghost"}`}
                aria-pressed={lang === l.code} onClick={() => setLang(l.code)}>
                {l.label}
              </button>
            ))}
          </div>
        </header>
        <main className="content">{children}</main>
      </div>
    </div>
  );
}

export function PageHeader({ title, desc, actions }: { title: string; desc?: string; actions?: ReactNode }) {
  return (
    <div className="page-header">
      <div>
        <h1>{title}</h1>
        {desc && <p>{desc}</p>}
      </div>
      {actions && <div className="actions">{actions}</div>}
    </div>
  );
}

export function Card({ title, desc, actions, children, flush, className = "" }: {
  title?: ReactNode; desc?: ReactNode; actions?: ReactNode; children: ReactNode; flush?: boolean; className?: string;
}) {
  return (
    <section className={`card ${flush ? "flush" : ""} ${className}`}>
      {(title || actions) && (
        <div className="card-header">
          <div>
            {title && <h2>{title}</h2>}
            {desc && <p>{desc}</p>}
          </div>
          {actions}
        </div>
      )}
      {children}
    </section>
  );
}

export function Stat({ icon, label, value, sub, tip }: {
  icon: ReactNode; label: string; value: ReactNode; sub?: ReactNode; tip?: string;
}) {
  return (
    <div className="card stat">
      <div className="label"><span className="icon">{icon}</span>{tip ? <span className="tip" data-tip={tip}>{label}</span> : label}</div>
      <div className="value">{value}</div>
      {sub && <div className="sub">{sub}</div>}
    </div>
  );
}
