/**
 * Format a duration in seconds into a human-readable string.
 * Rounds to the nearest whole second before formatting to prevent
 * floating-point artifacts like "1m 15.825000000000003s".
 *
 * Examples:
 *   49.592 -> "50s"
 *   75.825 -> "1m 16s"
 *   900    -> "15m 0s"
 *   3661   -> "1h 1m 1s"
 *   0      -> "-"
 *   null   -> "-"
 */
export function formatDuration(seconds: number | null | undefined): string {
  if (seconds == null || seconds < 0) return '-';
  const s = Math.round(seconds);
  if (s === 0) return '-';
  const hrs = Math.floor(s / 3600);
  const mins = Math.floor((s % 3600) / 60);
  const secs = s % 60;
  if (hrs > 0) return `${hrs}h ${mins}m ${secs}s`;
  if (mins > 0) return `${mins}m ${secs}s`;
  return `${secs}s`;
}

/**
 * Compute elapsed seconds between two ISO timestamps, or from startIso to now.
 * Returns null if startIso is missing.
 */
export function computeElapsed(startIso: string | null | undefined, endIso?: string | null): number | null {
  if (!startIso) return null;
  const start = new Date(startIso).getTime();
  const end = endIso ? new Date(endIso).getTime() : Date.now();
  const diff = (end - start) / 1000;
  return diff >= 0 ? diff : null;
}
