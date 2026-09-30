import { apiClient } from "./client";
import { controlPlaneURL } from "./config";
import type { RuntimeLogBatch, RuntimeLogSource } from "@/shared/types";

interface RuntimeLogDTO {
  logs: string[];
  next_offset: number;
  status: string;
  error_message: string;
  next_cursor?: string;
  has_more?: boolean;
  log_error?: string;
}

const runtimeLogPath = (source: RuntimeLogSource) => {
  if (source.kind === "build") return `/builds/${source.id}/logs/`;
  if (source.kind === "deployment") return `/deployments/${source.id}/logs/`;
  if (source.kind === "training") return `/training-jobs/${source.id}/logs/`;
  return `/drift-monitors/runs/${source.id}/logs/`;
};

export const getRuntimeLogs = async (
  source: RuntimeLogSource,
  offset: number,
  cursor?: string,
  signal?: AbortSignal,
): Promise<RuntimeLogBatch> => {
  const { data } = await apiClient.get<RuntimeLogDTO>(
    controlPlaneURL(runtimeLogPath(source)),
    {
      params: { offset, cursor },
      signal,
    },
  );
  return {
    logs: data.logs ?? [],
    nextOffset: data.next_offset ?? offset,
    nextCursor: data.next_cursor,
    hasMore: data.has_more ?? false,
    logError: data.log_error,
    status: data.status,
    error: data.error_message ?? "",
  };
};
