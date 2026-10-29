"use client";
import { useI18n } from "../lib/i18n";
import type { Lang } from "../lib/messages";

const LANGS: { code: Lang; label: string }[] = [
  { code: "en", label: "EN" },
  { code: "ko", label: "한국어" },
];

export function Nav() {
  const { lang, setLang, t } = useI18n();
  return (
    <nav className="topnav">
      <div>
        <a href="/">{t.nav.dashboard}</a>
        <a href="/scenarios">{t.nav.scenarios}</a>
        <a href="/approvals">{t.nav.approvals}</a>
      </div>
      <div className="lang-switch" role="group" aria-label={t.langLabel}>
        {LANGS.map((l) => (
          <button
            key={l.code}
            className={lang === l.code ? "" : "ghost"}
            aria-pressed={lang === l.code}
            onClick={() => setLang(l.code)}
          >
            {l.label}
          </button>
        ))}
      </div>
    </nav>
  );
}
