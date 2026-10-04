import { languageLocale } from "./language";
export function formatDateTime(
  value: string | number | Date,
  language: string,
  options?: Intl.DateTimeFormatOptions,
) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat(
    languageLocale(language),
    options ?? { dateStyle: "short", timeStyle: "medium" },
  ).format(date);
}
export function formatNumber(
  value: number,
  language: string,
  options?: Intl.NumberFormatOptions,
) {
  return new Intl.NumberFormat(languageLocale(language), options).format(value);
}
