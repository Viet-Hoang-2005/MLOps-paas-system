import { apiClient } from "@/shared/api/client";
import { controlPlaneURL } from "@/shared/api/config";
import type { MessageResponse } from "@/shared/types";
import type {
  ModelEndpointLogsResponse,
  ModelPredictionResponse,
  ModelProject,
  ModelProjectFormValues,
  ModelProjectListResponse,
  ModelProjectOverviewResponse,
} from "@/features/catalog/types";

const toModelProject = (project: ModelProject): ModelProject => {
  const endpoint = project.active_endpoint;
  return {
    ...project,
    endpoint_url: endpoint?.url ?? "",
  };
};

export const listModelProjects =
  async (): Promise<ModelProjectListResponse> => {
    const { data } = await apiClient.get<
      { results?: ModelProject[] } | ModelProject[]
    >(controlPlaneURL("/models/"));
    return {
      models: (Array.isArray(data) ? data : (data.results ?? [])).map(
        toModelProject,
      ),
    };
  };

export const getModelProject = async (modelId: string): Promise<ModelProject> =>
  toModelProject(
    (await apiClient.get<ModelProject>(controlPlaneURL(`/models/${modelId}/`)))
      .data,
  );

export const createModelProject = async (
  payload: ModelProjectFormValues,
): Promise<ModelProject> => {
  const { data } = await apiClient.post<ModelProject>(
    controlPlaneURL("/models/"),
    {
      name: payload.name,
      description: payload.description,
      access_mode: payload.access_mode,
    },
  );
  return data;
};

export const updateModelProject = async (
  modelId: string,
  payload: ModelProjectFormValues,
): Promise<ModelProject> =>
  (
    await apiClient.patch<ModelProject>(controlPlaneURL(`/models/${modelId}/`), {
      name: payload.name,
      description: payload.description,
      access_mode: payload.access_mode,
    })
  ).data;

export const deleteModelProject = async (
  modelId: string,
  force = false,
): Promise<MessageResponse> =>
  (
    await apiClient.delete<MessageResponse>(
      controlPlaneURL(`/models/${modelId}/${force ? "?force=true" : ""}`),
    )
  ).data;

export const predictWithModelProject = async (
  endpointUrl: string,
  features: Record<string, unknown>,
): Promise<ModelPredictionResponse> =>
  (await apiClient.post<ModelPredictionResponse>(endpointUrl, { features }))
    .data;

export const getModelEndpointLogs = async (
  modelId: string,
): Promise<ModelEndpointLogsResponse> => {
  const versions = await apiClient.get<{ results?: Array<{ id: string }> }>(
    controlPlaneURL(`/registry/models/${modelId}/versions/`),
  );
  const versionIds = new Set(
    (versions.data.results ?? []).map((version) => version.id),
  );
  const { data: endpointPage } = await apiClient.get<{
    results?: Array<{ id: string; version_id: string; runtime_name: string }>;
  }>(controlPlaneURL("/endpoints/"));
  const endpoint = (endpointPage.results ?? []).find((item) =>
    versionIds.has(item.version_id),
  );
  if (!endpoint) return { project_id: modelId, container_name: "", logs: "" };
  const { data } = await apiClient.get<{ runtime_name: string; logs: string }>(
    controlPlaneURL(`/endpoints/${endpoint.id}/logs/`),
  );
  return {
    project_id: modelId,
    container_name: data.runtime_name,
    logs: data.logs,
  };
};

export const getProjectOverview = async (
  projectId: string,
): Promise<ModelProjectOverviewResponse> =>
  (
    await apiClient.get<ModelProjectOverviewResponse>(
      controlPlaneURL(`/models/${projectId}/overview/`),
    )
  ).data;
