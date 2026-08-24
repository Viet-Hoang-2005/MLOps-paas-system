import { apiClient } from '@/shared/api/client';
import { controlPlaneURL } from '@/shared/api/config';
import type { MessageResponse } from '@/shared/types';
import type {
  ModelEndpointLogsResponse,
  ModelPredictionResponse,
  ModelProject,
  ModelProjectFormValues,
  ModelProjectListResponse,
} from '@/features/catalog/types';

export interface WorkspaceFile {
  key: string;
  relative_path: string;
  size_bytes: number;
  updated_at: string;
  download_url: string;
}

interface WorkspaceFileDTO {
  relative_path: string;
  size_bytes: number;
  updated_at: string;
  download_url: string;
}

const toWorkspaceFile = (file: WorkspaceFileDTO): WorkspaceFile => ({
  ...file,
  key: file.relative_path,
});

const toModelProject = (project: ModelProject): ModelProject => {
  const endpoint = project.active_endpoint;
  const endpointStatus = endpoint?.deployment_status === 'deploying' || endpoint?.deployment_status === 'pending'
    ? 'deploying'
    : endpoint?.health_status === 'healthy'
      ? 'healthy'
      : endpoint
        ? 'unhealthy'
        : 'not_deployed';
  return {
    ...project,
    endpoint_url: endpoint?.url ?? '',
    health_url: endpoint?.health_url ?? '',
    endpoint_status: endpointStatus,
    deployment_id: endpoint?.deployment_id,
    endpoint_last_checked_at: endpoint?.last_checked_at ?? null,
  };
};

export const listModelProjects = async (): Promise<ModelProjectListResponse> => {
  const { data } = await apiClient.get<{ results?: ModelProject[] } | ModelProject[]>(controlPlaneURL('/models/'));
  return { models: (Array.isArray(data) ? data : data.results ?? []).map(toModelProject) };
};

export const getModelProject = async (modelId: string): Promise<ModelProject> =>
  toModelProject((await apiClient.get<ModelProject>(controlPlaneURL(`/models/${modelId}/`))).data);

export const createModelProject = async (payload: ModelProjectFormValues): Promise<ModelProject> => {
  const { data } = await apiClient.post<ModelProject>(controlPlaneURL('/models/'), {
    name: payload.name,
    description: payload.description,
    access_mode: payload.access_mode,
  });
  if (payload.source_code_file) {
    await uploadSourceCodeFile(data.id, payload.source_code_file, payload.source_code_file.name);
  }
  if (payload.reference_data_file) {
    await uploadReferenceFile(data.id, payload.reference_data_file, payload.reference_data_file.name);
  }
  if (payload.artifact) {
    const versionData = new FormData();
    versionData.append('version', payload.version || '1');
    versionData.append('source_artifact', payload.artifact);
    await apiClient.post(controlPlaneURL(`/registry/models/${data.id}/versions/`), versionData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
  }
  return data;
};

export const updateModelProject = async (
  modelId: string,
  payload: ModelProjectFormValues,
): Promise<ModelProject> =>
  (await apiClient.put<ModelProject>(controlPlaneURL(`/models/${modelId}/`), {
    name: payload.name,
    description: payload.description,
    access_mode: payload.access_mode,
  })).data;

export const deleteModelProject = async (modelId: string, force = false): Promise<MessageResponse> =>
  (await apiClient.delete<MessageResponse>(controlPlaneURL(`/models/${modelId}/${force ? '?force=true' : ''}`))).data;

export const predictWithModelProject = async (
  endpointUrl: string,
  features: Record<string, unknown>,
): Promise<ModelPredictionResponse> =>
  (await apiClient.post<ModelPredictionResponse>(endpointUrl, { features })).data;

export const getModelEndpointLogs = async (modelId: string): Promise<ModelEndpointLogsResponse> => {
  const versions = await apiClient.get<{ results?: Array<{ id: string }> }>(
    controlPlaneURL(`/registry/models/${modelId}/versions/`),
  );
  const versionIds = new Set((versions.data.results ?? []).map((version) => version.id));
  const { data: endpointPage } = await apiClient.get<{
    results?: Array<{ id: string; version_id: string; runtime_name: string }>;
  }>(controlPlaneURL('/endpoints/'));
  const endpoint = (endpointPage.results ?? []).find((item) => versionIds.has(item.version_id));
  if (!endpoint) return { project_id: modelId, container_name: '', logs: '' };
  const { data } = await apiClient.get<{ runtime_name: string; logs: string }>(
    controlPlaneURL(`/endpoints/${endpoint.id}/logs/`),
  );
  return { project_id: modelId, container_name: data.runtime_name, logs: data.logs };
};

export const listSourceCodeFiles = async (modelId: string): Promise<WorkspaceFile[]> =>
  (await apiClient.get<WorkspaceFileDTO[]>(controlPlaneURL(`/models/${modelId}/workspace/code/files/`)))
    .data.map(toWorkspaceFile);

export const uploadSourceCodeFile = async (
  modelId: string,
  file: File,
  path: string,
): Promise<{ message: string }> => {
  const formData = new FormData();
  formData.append('file', file);
  formData.append('relative_path', path);
  return (await apiClient.post<{ message: string }>(
    controlPlaneURL(`/models/${modelId}/workspace/code/files/`),
    formData,
    { headers: { 'Content-Type': 'multipart/form-data' } },
  )).data;
};

export const deleteSourceCodeFile = async (modelId: string, path: string): Promise<MessageResponse> =>
  (await apiClient.delete<MessageResponse>(controlPlaneURL(`/models/${modelId}/workspace/code/files/`), {
    data: { relative_path: path },
  })).data;

export const listReferenceFiles = async (modelId: string): Promise<WorkspaceFile[]> =>
  (await apiClient.get<WorkspaceFileDTO[]>(controlPlaneURL(`/models/${modelId}/workspace/data/files/`)))
    .data.map(toWorkspaceFile);

export const uploadReferenceFile = async (
  modelId: string,
  file: File,
  path: string,
): Promise<{ message: string }> => {
  const formData = new FormData();
  formData.append('file', file);
  formData.append('relative_path', path);
  return (await apiClient.post<{ message: string }>(
    controlPlaneURL(`/models/${modelId}/workspace/data/files/`),
    formData,
    { headers: { 'Content-Type': 'multipart/form-data' } },
  )).data;
};

export const deleteReferenceFile = async (modelId: string, path: string): Promise<MessageResponse> =>
  (await apiClient.delete<MessageResponse>(controlPlaneURL(`/models/${modelId}/workspace/data/files/`), {
    data: { relative_path: path },
  })).data;
