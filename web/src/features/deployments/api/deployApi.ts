import { apiClient } from "@/shared/api/client";
import { controlPlaneURL } from "@/shared/api/config";
import { fetchAllPages } from "@/shared/api/pagination";
import type {
  Build,
  Deployment,
  ModelVersion,
} from "@/features/projects/types";
export const getBuild = async (id: string): Promise<Build> =>
  (await apiClient.get<Build>(controlPlaneURL(`/builds/${id}/`))).data;
export const cancelBuildById = async (id: string): Promise<Build> =>
  (await apiClient.post<Build>(controlPlaneURL(`/builds/${id}/cancel/`))).data;
export const rebuildById = async (id: string): Promise<Build> =>
  (await apiClient.post<Build>(controlPlaneURL(`/builds/${id}/rebuild/`))).data;
export const deleteBuildById = async (id: string): Promise<Build> =>
  (await apiClient.delete<Build>(controlPlaneURL(`/builds/${id}/`))).data;
export const listProjectBuilds = async (id: string): Promise<Build[]> =>
  (await apiClient.get<Build[]>(controlPlaneURL(`/models/${id}/builds/`))).data;
export const deployBuild = async (id: string): Promise<Deployment> =>
  (
    await apiClient.post<Deployment>(controlPlaneURL("/deployments/"), {
      build: id,
    })
  ).data;
export const getProjectVersions = (id: string): Promise<ModelVersion[]> =>
  fetchAllPages<ModelVersion>(
    controlPlaneURL(`/registry/models/${id}/versions/`),
  );
export const listBuilds = (): Promise<Build[]> =>
  fetchAllPages<Build>(controlPlaneURL("/builds/"));
export const listDeployments = (): Promise<Deployment[]> =>
  fetchAllPages<Deployment>(controlPlaneURL("/deployments/"));
