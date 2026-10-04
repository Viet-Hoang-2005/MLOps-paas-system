export type Language = "en" | "vi";
export const LANGUAGE_STORAGE_KEY = "adaptml.language";
export function normalizeLanguage(
  value: string | null | undefined,
): Language | null {
  const language = value?.toLowerCase().split(/[-_]/)[0];
  return language === "en" || language === "vi" ? language : null;
}
export function detectLanguage(
  storage: Pick<Storage, "getItem"> | undefined,
  languages: readonly string[],
): Language {
  try {
    const stored = normalizeLanguage(storage?.getItem(LANGUAGE_STORAGE_KEY));
    if (stored) return stored;
  } catch {
    /* Storage may be unavailable in private browsing. */
  }
  for (const value of languages) {
    const language = normalizeLanguage(value);
    if (language) return language;
  }
  return "en";
}
export function persistLanguage(
  storage: Pick<Storage, "setItem"> | undefined,
  language: Language,
) {
  try {
    storage?.setItem(LANGUAGE_STORAGE_KEY, language);
  } catch {
    /* Keep the in-memory choice. */
  }
}
export const languageLocale = (language: string) =>
  normalizeLanguage(language) === "vi" ? "vi-VN" : "en-US";
