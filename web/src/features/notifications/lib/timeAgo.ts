export function formatTimeAgo(isoString: string, locale: string = "vi"): string {
  try {
    const date = new Date(isoString);
    if (Number.isNaN(date.getTime())) {
      return isoString;
    }
    const now = new Date();
    const diffSeconds = Math.round((date.getTime() - now.getTime()) / 1000);

    const absSeconds = Math.abs(diffSeconds);
    const rtf = new Intl.RelativeTimeFormat(locale === "vi" ? "vi-VN" : "en-US", {
      numeric: "auto",
    });

    if (absSeconds < 60) {
      return locale === "vi" ? "Vừa xong" : "Just now";
    }
    if (absSeconds < 3600) {
      return rtf.format(Math.round(diffSeconds / 60), "minute");
    }
    if (absSeconds < 86400) {
      return rtf.format(Math.round(diffSeconds / 3600), "hour");
    }
    if (absSeconds < 2592000) {
      return rtf.format(Math.round(diffSeconds / 86400), "day");
    }
    return date.toLocaleDateString(locale === "vi" ? "vi-VN" : "en-US", {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return isoString;
  }
}

