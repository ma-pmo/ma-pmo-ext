// The API sends times in UTC, some without a zone ("2026-11-08T00:50:57"). Read those as UTC, not
// as local time, and show them in the reader's time zone in the UI language.
export function when(iso?: string | null, lang = "en"): string {
  if (!iso) return "";
  const zoned = /(Z|[+-]\d\d:?\d\d)$/i.test(iso) ? iso : `${iso}Z`;
  return new Date(zoned).toLocaleString(lang === "ko" ? "ko-KR" : "en-US",
    { dateStyle: "medium", timeStyle: "short" });
}
