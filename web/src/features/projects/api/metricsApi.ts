import { apiClient } from "@/shared/api/client";
import { controlPlaneURL } from "@/shared/api/config";
export interface MetricSeries {
  values: Array<[number, string]>;
}
export interface RuntimeMetricsResponse {
  status: "available" | "unavailable" | "no_data";
  deployment_id: string | null;
  series: Partial<Record<"cpu" | "memory" | "requests", MetricSeries[]>>;
}
export async function getRuntimeMetrics(projectId: string, window: string) {
  return (
    await apiClient.get<RuntimeMetricsResponse>(
      controlPlaneURL(`/observability/models/${projectId}/runtime-metrics/`),
      { params: { window } },
    )
  ).data;
}
