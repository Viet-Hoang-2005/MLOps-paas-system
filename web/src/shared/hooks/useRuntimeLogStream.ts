import { useEffect, useState } from 'react';
import { getRuntimeLogs } from '@/shared/api/runtimeLogs';
import type { RuntimeLogSource, RuntimeStatus } from '@/shared/types';

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
}

export function useRuntimeLogStream({
  source,
  enabled = true,
  terminalStatuses = [],
  pollIntervalMs = 1500,
}: RuntimeLogStreamOptions): RuntimeLogStream {
  const sourceKind = source?.kind;
  const sourceId = source?.id;
  const sourceKey = sourceKind && sourceId ? `${sourceKind}:${sourceId}` : '';
  const terminalStatusesKey = terminalStatuses.join('\u0000');
  const [state, setState] = useState<{
    sourceKey: string;
    logs: string[];
    status: RuntimeStatus | null;
    error: string;
  }>({ sourceKey, logs: [], status: null, error: '' });
  const current = state.sourceKey === sourceKey
    ? state
    : { sourceKey, logs: [], status: null, error: '' };

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let offset = 0;
    const terminalStatusSet = new Set(terminalStatusesKey ? terminalStatusesKey.split('\u0000') : []);

    if (!sourceKind || !sourceId || !enabled) return;
    const activeSource = { kind: sourceKind, id: sourceId } as RuntimeLogSource;

    const poll = async () => {
      try {
        const batch = await getRuntimeLogs(activeSource, offset);
        if (cancelled) return;

        const nextLogs = batch.logs.filter((line) => !line.startsWith('BUILD_EOF_'));
        offset = batch.nextOffset;
        setState((previous) => ({
          sourceKey,
          logs: previous.sourceKey === sourceKey ? [...previous.logs, ...nextLogs] : nextLogs,
          status: batch.status,
          error: batch.error,
        }));

        if (terminalStatusSet.has(batch.status)) return;
      } catch {
        // Runtime log polling is best-effort. Retry transient failures.
      }

      if (!cancelled) timer = setTimeout(poll, pollIntervalMs);
    };

    void poll();

    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [enabled, pollIntervalMs, sourceId, sourceKey, sourceKind, terminalStatusesKey]);

  return {
    logs: current.logs,
    status: current.status,
    error: current.error,
    isPolling: Boolean(
      enabled
      && sourceKey
      && !terminalStatuses.includes(current.status ?? ''),
    ),
  };
}
