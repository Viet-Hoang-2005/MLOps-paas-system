import { formatDuration } from "@/shared/lib/formatDuration";

export function formatQuotaDuration(seconds: number): string {
  return seconds === 0 ? "0s" : formatDuration(seconds);
}
