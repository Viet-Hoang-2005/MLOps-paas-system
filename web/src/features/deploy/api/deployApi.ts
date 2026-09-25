import { apiClient } from "@/shared/api/client";
import { controlPlaneURL } from "@/shared/api/config";
import { pageResults } from "@/shared/api/pagination";
import type { ModelProject } from "@/features/catalog/types";
import type { Build, Deployment, ModelVersion, ProjectMetadataForm } from "@/features/catalog/types";

export const createProjectMetadata = async (payload: ProjectMetadataForm): Promise<ModelProject> =>
  (await apiClient.post<ModelProject>(controlPlaneURL("/models/"), {
    name: payload.name,
    description: payload.description,
    access_mode: payload.access_mode,
  })).data;

export const updateProjectMetadata = async (projectId: string, payload: ProjectMetadataForm): Promise<ModelProject> =>
  (await apiClient.patch<ModelProject>(controlPlaneURL(`/models/${projectId}/`), {
    name: payload.name,
    description: payload.description,
    access_mode: payload.access_mode,
  })).data;

export const getBuild = async (buildId: string): Promise<Build> =>
  (await apiClient.get<Build>(controlPlaneURL(`/builds/${buildId}/`))).data;

export const cancelBuildById = async (buildId: string): Promise<Build> =>
  (await apiClient.post<Build>(controlPlaneURL(`/builds/${buildId}/cancel/`))).data;

export const listProjectBuilds = async (projectId: string): Promise<Build[]> => {
  const { data } = await apiClient.get<{ results: Build[] } | Build[]>(controlPlaneURL(`/models/${projectId}/builds/`));
  return pageResults(data);
};

export const deployBuild = async (versionId: string, target: "staging" | "production"): Promise<Deployment> =>
  (await apiClient.post<Deployment>(controlPlaneURL("/deployments/"), { version: versionId, target })).data;

export const getProjectVersions = async (projectId: string): Promise<ModelVersion[]> => {
  const { data } = await apiClient.get<{ results: ModelVersion[] } | ModelVersion[]>(controlPlaneURL(`/registry/models/${projectId}/versions/`));
  return pageResults(data);
};

export const listBuilds = async (): Promise<Build[]> => {
  const { data } = await apiClient.get<{ results: Build[] } | Build[]>(controlPlaneURL("/builds/"));
  return pageResults(data);
};

export const listDeployments = async (): Promise<Deployment[]> => {
  const { data } = await apiClient.get<{ results: Deployment[] } | Deployment[]>(controlPlaneURL("/deployments/"));
  return pageResults(data);
};
