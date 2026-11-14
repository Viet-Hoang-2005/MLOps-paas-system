/** Progress events retain one mutable display row; ordinary log records stay append-only. */
export function terminalLines(logs: readonly string[]): string[] {
  const lines: string[] = [];
  let progressRow: number | undefined;
  for (const log of logs) {
    if (log.startsWith("TERMINAL_PROGRESS ")) {
      try {
        const event: unknown = JSON.parse(
          log.slice("TERMINAL_PROGRESS ".length),
        );
        if (
          event &&
          typeof event === "object" &&
          "text" in event &&
          typeof event.text === "string" &&
          "done" in event &&
          typeof event.done === "boolean"
        ) {
          if (progressRow === undefined) {
            progressRow = lines.length;
            lines.push(event.text);
          } else lines[progressRow] = event.text;
          if (event.done) progressRow = undefined;
          continue;
        }
      } catch {
        /* Render malformed records as plain text. */
      }
    }
    progressRow = undefined;
    lines.push(log);
  }
  return lines;
}
