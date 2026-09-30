import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { getRuntimeLogs } from "@/shared/api/runtimeLogs";
import type { RuntimeLogSource, RuntimeStatus } from "@/shared/types";

interface RuntimeLogStreamOptions {
  source?: RuntimeLogSource | null;
  enabled?: boolean;
  terminalStatuses?: readonly string[];
  pollIntervalMs?: number;
}

export interface RuntimeLogStream {
  logs: string[];
  status: RuntimeStatus | null;
  error: string;
  isPolling: boolean;
  refresh: () => void;
}

export function useRuntimeLogStream({
  source,
  enabled = true,
  terminalStatuses = [],
  pollIntervalMs = 2000,
}: RuntimeLogStreamOptions): RuntimeLogStream {
  const { t } = useTranslation("common");
  const [refreshKey, setRefreshKey] = useState(0);
  const sourceKind = source?.kind;
  const sourceId = source?.id;
  const sourceKey = sourceKind && sourceId ? `${sourceKind}:${sourceId}` : "";
  const terminalStatusesKey = terminalStatuses.join("\u0000");
  const [state, setState] = useState<{
    sourceKey: string;
    logs: string[];
    status: RuntimeStatus | null;
    error: string;
  }>({ sourceKey, logs: [], status: null, error: "" });
  const current =
    state.sourceKey === sourceKey
      ? state
      : { sourceKey, logs: [], status: null, error: "" };

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let offset = 0;
    let cursor: string | undefined;
    let receivedFirstBatch = false;
    let terminalSince: number | undefined;
    const controller = new AbortController();
    const terminalStatusSet = new Set(
      terminalStatusesKey ? terminalStatusesKey.split("\u0000") : [],
    );

    if (!sourceKind || !sourceId || !enabled) return;
    const activeSource = { kind: sourceKind, id: sourceId } as RuntimeLogSource;

    const poll = async () => {
      try {
        const batch = await getRuntimeLogs(activeSource, offset, cursor, controller.signal);
        if (cancelled) return;

        const nextLogs = batch.logs.filter(
          (line) => !line.startsWith("BUILD_EOF_"),
        );
        offset = batch.nextOffset;
        cursor = batch.nextCursor;
        const append = receivedFirstBatch;
        receivedFirstBatch = true;
        setState((previous) => ({
          sourceKey,
          logs:
            append && previous.sourceKey === sourceKey
              ? [...previous.logs, ...nextLogs].slice(-10000)
              : nextLogs,
          status: batch.status,
          error: batch.error || (batch.logError ? t("terminal.logsUnavailable") : ""),
        }));

        if (terminalStatusSet.has(batch.status)) {
          terminalSince ??= Date.now();
          // Drain exit-handler logs after the authoritative result has arrived.
          if (!batch.hasMore && Date.now() - terminalSince >= 15000) return;
        } else terminalSince = undefined;
        if (batch.hasMore) {
          timer = setTimeout(poll, 100);
          return;
        }
      } catch {
        if (cancelled) return;
        setState((previous) => ({
          sourceKey,
          logs: previous.sourceKey === sourceKey ? previous.logs : [],
          status: previous.sourceKey === sourceKey ? previous.status : null,
          error: t("terminal.logsUnavailable"),
        }));
        // Keep the cursor and retry without losing collected output.
      }

      if (!cancelled) timer = setTimeout(poll, pollIntervalMs);
    };

    void poll();

    return () => {
      cancelled = true;
      controller.abort();
      if (timer) clearTimeout(timer);
    };
  }, [
    enabled,
    pollIntervalMs,
    sourceId,
    sourceKey,
    sourceKind,
    terminalStatusesKey,
    refreshKey,
    t,
  ]);

  return {
    logs: current.logs,
    status: current.status,
    error: current.error,
    isPolling: Boolean(
      enabled && sourceKey && !terminalStatuses.includes(current.status ?? ""),
    ),
    refresh: () => setRefreshKey((value) => value + 1),
  };
}
