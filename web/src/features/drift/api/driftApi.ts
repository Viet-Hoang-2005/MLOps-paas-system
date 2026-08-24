import { apiClient } from '@/shared/api/client';
import { controlPlaneURL } from '@/shared/api/config';
import { pageResults } from '@/shared/api/pagination';
import { getProjectVersions } from '@/features/deploy/api/deployApi';
import type {
  DriftMonitoringJob,
  DriftMonitoringResult,
  DriftMonitorInput,
  ProductionDataRecord,
  WorkspaceDataFile,
} from '@/features/drift/types';

export const listProductionData = async (
  projectId: string,
  limit?: number,
): Promise<ProductionDataRecord[]> =>
  (await apiClient.get<ProductionDataRecord[]>(
    controlPlaneURL(`/models/${projectId}/production-data/`),
    { params: limit === undefined ? undefined : { limit } },
  )).data;

export const listDriftMonitoringJobs = async (modelId: string): Promise<DriftMonitoringJob[]> => {
  const { data } = await apiClient.get<{ results: DriftMonitoringJob[] } | DriftMonitoringJob[]>(
    controlPlaneURL('/drift-monitors/'),
  );
  return pageResults(data).filter((monitor) => monitor.project_id === modelId);
};

export const listDriftMonitoringResults = async (jobId: string): Promise<DriftMonitoringResult[]> =>
  (await apiClient.get<DriftMonitoringJob>(controlPlaneURL(`/drift-monitors/${jobId}/`))).data.runs ?? [];

const resolveMonitorInputs = async (projectId: string, referencePath: string) => {
  const [versions, { data: files }] = await Promise.all([
    getProjectVersions(projectId),
    apiClient.get<WorkspaceDataFile[]>(controlPlaneURL(`/models/${projectId}/workspace/data/files/`)),
  ]);
  const version = versions[0];
  const file = files.find(
    (item) => item.id === referencePath || item.relative_path === referencePath || item.s3_uri === referencePath,
  );
  if (!version) throw new Error('Register a model version before configuring drift monitoring.');
  if (!file) throw new Error('Select reference data from the project workspace.');
  return { version, file };
};

export const createDriftMonitoringJob = async (payload: DriftMonitorInput): Promise<DriftMonitoringJob> => {
  const { version, file } = await resolveMonitorInputs(payload.project_id, payload.reference_data_s3_path);
  return (await apiClient.post<DriftMonitoringJob>(controlPlaneURL('/drift-monitors/'), {
    version: version.id,
    reference_asset: file.id,
    name: 'default',
    trigger_threshold: payload.trigger_threshold,
  })).data;
};

export const updateDriftMonitoringJob = async (
  payload: DriftMonitorInput & { id: string },
): Promise<DriftMonitoringJob> => {
  const { version, file } = await resolveMonitorInputs(payload.project_id, payload.reference_data_s3_path);
  return (await apiClient.put<DriftMonitoringJob>(controlPlaneURL(`/drift-monitors/${payload.id}/`), {
    version: version.id,
    reference_asset: file.id,
    name: 'default',
    trigger_threshold: payload.trigger_threshold,
    is_active: true,
  })).data;
};

export const deleteDriftMonitoringJob = async (id: string): Promise<void> => {
  await apiClient.delete(controlPlaneURL(`/drift-monitors/${id}/`));
};

export const runDriftMonitoringJob = async (id: string): Promise<DriftMonitoringResult> =>
  (await apiClient.post<DriftMonitoringResult>(
    controlPlaneURL(`/drift-monitors/${id}/runs/`),
    undefined,
    { headers: { 'Idempotency-Key': crypto.randomUUID() } },
  )).data;

export const listReferenceFiles = async (modelId: string): Promise<WorkspaceDataFile[]> =>
  (await apiClient.get<WorkspaceDataFile[]>(
    controlPlaneURL(`/models/${modelId}/workspace/data/files/`),
  )).data;

export const uploadReferenceData = async (modelId: string, file: File): Promise<unknown> => {
  const formData = new FormData();
  formData.append('file', file);
  formData.append('relative_path', file.name);
  return (await apiClient.post(
    controlPlaneURL(`/models/${modelId}/workspace/data/files/`),
    formData,
    { headers: { 'Content-Type': 'multipart/form-data' } },
  )).data;
};

export const getDriftReportDownloadUrl = async (runId: string): Promise<string> =>
  (await apiClient.get<{ url: string }>(
    controlPlaneURL(`/drift-monitors/runs/${runId}/report-url/`),
  )).data.url;
