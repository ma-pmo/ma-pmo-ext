"use client";
// Language context: English by default, Korean optional.
// Priority: ?lang= in the URL > saved choice > browser language > English.
import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { setApiLang } from "./api";
import { MESSAGES, type Lang, type Messages } from "./messages";

const STORAGE_KEY = "ma-pmo-lang";

type Ctx = { lang: Lang; setLang: (l: Lang) => void; t: Messages };
const I18nContext = createContext<Ctx>({ lang: "en", setLang: () => {}, t: MESSAGES.en });

function asLang(v: string | null | undefined): Lang | null {
  const code = (v || "").toLowerCase().slice(0, 2);
  return code === "ko" || code === "en" ? code : null;
}

function detect(): Lang {
  const fromUrl = asLang(new URLSearchParams(window.location.search).get("lang"));
  if (fromUrl) return fromUrl;
  try {
    const saved = asLang(window.localStorage.getItem(STORAGE_KEY));
    if (saved) return saved;
  } catch {
    // storage may be blocked (private mode); fall through
  }
  return asLang(navigator.language) ?? "en";
}

export function LanguageProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>("en");
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const l = detect();
    setApiLang(l);
    setLangState(l);
    setReady(true);
  }, []);

  useEffect(() => {
    document.documentElement.lang = lang;
    document.title = MESSAGES[lang].appTitle;
  }, [lang]);

  const setLang = (l: Lang) => {
    setApiLang(l);
    setLangState(l);
    try {
      window.localStorage.setItem(STORAGE_KEY, l);
    } catch {
      // ignore
    }
  };

  // Render children only after the language is known so pages fetch data in that language.
  return (
    <I18nContext.Provider value={{ lang, setLang, t: MESSAGES[lang] }}>
      {ready ? children : null}
    </I18nContext.Provider>
  );
}

export function useI18n() {
  return useContext(I18nContext);
}
