import { apiClient } from "@/shared/api/client";
import { controlPlaneURL } from "@/shared/api/config";
import type { Build, Deployment } from "@/features/projects/types";

export async function buildPreview(
  projectId: string,
  revision: number,
): Promise<Build> {
  return (
    await apiClient.post<Build>(
      controlPlaneURL(`/models/${projectId}/builds/`),
      { revision },
    )
  ).data;
}
export async function buildTraining(
  jobId: string,
  outputRevision: number,
): Promise<Build> {
  return (
    await apiClient.post<Build>(
      controlPlaneURL(`/training-jobs/${jobId}/build/`),
      { output_revision: outputRevision },
    )
  ).data;
}
export const registerBuild = async (buildId: string) =>
  (await apiClient.post<Build>(controlPlaneURL(`/builds/${buildId}/register/`)))
    .data;
export const getDeployment = async (id: string) =>
  (await apiClient.get<Deployment>(controlPlaneURL(`/deployments/${id}/`)))
    .data;
