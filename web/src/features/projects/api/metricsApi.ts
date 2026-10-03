import { apiClient } from "@/shared/api/client";
import { controlPlaneURL } from "@/shared/api/config";
export interface MetricSeries {
  values: Array<[number, string]>;
}
export interface RuntimeMetricsResponse {
  mode: "realtime" | "history";
  status: "available" | "unavailable" | "no_data";
  deployment_id: string | null;
  series?: Partial<Record<"cpu" | "memory" | "requests", MetricSeries[]>>;
  snapshot?: {
    timestamp: number;
    cpu: number | null;
    memory: number | null;
    request_counter: { count: number; generation: string } | null;
  } | null;
}
export async function getRuntimeMetrics(
  projectId: string,
  window: string,
  signal?: AbortSignal,
) {
  return (
    await apiClient.get<RuntimeMetricsResponse>(
      controlPlaneURL(`/observability/models/${projectId}/runtime-metrics/`),
      { params: { window }, signal },
    )
  ).data;
}
