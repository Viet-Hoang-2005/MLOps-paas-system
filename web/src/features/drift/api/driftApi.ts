import { apiClient } from "@/shared/api/client";
import { controlPlaneURL } from "@/shared/api/config";
import { pageResults } from "@/shared/api/pagination";
import type {
  DriftMonitoringJob,
  DriftMonitoringResult,
  DriftMonitorInput,
  ProductionDataRecord,
} from "@/features/drift/types";

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
  const { data } = await apiClient.get<
    { results: DriftMonitoringJob[] } | DriftMonitoringJob[]
  >(controlPlaneURL("/drift-monitors/"));
  return pageResults(data).filter((monitor) => monitor.project_id === modelId);
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
  return (
    await apiClient.post<DriftMonitoringJob>(
      controlPlaneURL("/drift-monitors/"),
      {
        version: payload.version_id,
        name: "default",
        trigger_threshold: payload.trigger_threshold,
      },
    )
  ).data;
};

export const updateDriftMonitoringJob = async (
  payload: DriftMonitorInput & { id: string },
): Promise<DriftMonitoringJob> => {
  return (
    await apiClient.put<DriftMonitoringJob>(
      controlPlaneURL(`/drift-monitors/${payload.id}/`),
      {
        version: payload.version_id,
        name: "default",
        trigger_threshold: payload.trigger_threshold,
        is_active: true,
      },
    )
  ).data;
};

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
