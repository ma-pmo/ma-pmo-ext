// The API sends times in UTC, some without a zone ("2026-11-08T00:50:57"). Read those as UTC, not
// as local time, and show them in the reader's time zone in the UI language.
const utc = (iso: string) => new Date(/(Z|[+-]\d\d:?\d\d)$/i.test(iso) ? iso : `${iso}Z`);
const locale = (lang: string) => (lang === "ko" ? "ko-KR" : "en-US");

export function when(iso?: string | null, lang = "en"): string {
  if (!iso) return "";
  return utc(iso).toLocaleString(locale(lang), { dateStyle: "medium", timeStyle: "short" });
}

// the time of day only, with seconds (audit log rows)
export function clock(iso?: string | null, lang = "en"): string {
  return iso ? utc(iso).toLocaleTimeString(locale(lang), { timeStyle: "medium" }) : "";
}
