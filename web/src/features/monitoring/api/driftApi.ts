import { apiClient } from "@/shared/api/client";
import { controlPlaneURL } from "@/shared/api/config";
import { fetchAllPages } from "@/shared/api/pagination";
import type {
  DriftMonitoringJob,
  DriftMonitoringResult,
  DriftMonitorInput,
  ProductionDataRecord,
} from "@/features/monitoring/types";

export const listProductionData = async (
  projectId: string,
  limit?: number,
): Promise<ProductionDataRecord[]> =>
  (
    await apiClient.get<ProductionDataRecord[]>(
      controlPlaneURL(`/models/${projectId}/production-data/`),
      { params: limit === undefined ? undefined : { limit } },
    )
  ).data;

export const listDriftMonitoringJobs = async (
  modelId: string,
): Promise<DriftMonitoringJob[]> => {
  const data = await fetchAllPages<DriftMonitoringJob>(
    controlPlaneURL("/drift-monitors/"),
  );
  return data.filter((monitor) => monitor.project_id === modelId);
};

export const listDriftMonitoringResults = async (
  jobId: string,
): Promise<DriftMonitoringResult[]> =>
  (
    await apiClient.get<DriftMonitoringJob>(
      controlPlaneURL(`/drift-monitors/${jobId}/`),
    )
  ).data.runs ?? [];

export const createDriftMonitoringJob = async (
  payload: DriftMonitorInput,
): Promise<DriftMonitoringJob> => {
  const data = new FormData();
  data.append("version", payload.version_id);
  data.append("name", "default");
  data.append("trigger_threshold", String(payload.trigger_threshold));
  if (payload.reference_file)
    data.append("reference_file", payload.reference_file);
  return (
    await apiClient.post<DriftMonitoringJob>(
      controlPlaneURL("/drift-monitors/"),
      data,
    )
  ).data;
};

export const updateDriftMonitoringJob = async (
  payload: DriftMonitorInput & { id: string },
): Promise<DriftMonitoringJob> =>
  (
    await apiClient.patch<DriftMonitoringJob>(
      controlPlaneURL(`/drift-monitors/${payload.id}/`),
      { trigger_threshold: payload.trigger_threshold },
    )
  ).data;

export const getDriftMonitor = async (
  id: string,
): Promise<DriftMonitoringJob> =>
  (
    await apiClient.get<DriftMonitoringJob>(
      controlPlaneURL(`/drift-monitors/${id}/`),
    )
  ).data;

export const deleteDriftMonitoringJob = async (id: string): Promise<void> => {
  await apiClient.delete(controlPlaneURL(`/drift-monitors/${id}/`));
};

export const runDriftMonitoringJob = async (
  id: string,
): Promise<DriftMonitoringResult> =>
  (
    await apiClient.post<DriftMonitoringResult>(
      controlPlaneURL(`/drift-monitors/${id}/runs/`),
      undefined,
      { headers: { "Idempotency-Key": crypto.randomUUID() } },
    )
  ).data;

export const getDriftReportDownloadUrl = async (
  runId: string,
): Promise<string> =>
  (
    await apiClient.get<{ url: string }>(
      controlPlaneURL(`/drift-monitors/runs/${runId}/report-url/`),
    )
  ).data.url;
