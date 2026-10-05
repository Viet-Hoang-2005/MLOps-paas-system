import { apiClient } from "@/shared/api/client";
import { controlPlaneURL } from "@/shared/api/config";
import type { ModelVersion } from "@/features/projects/types";

export async function getVersionDetail(id: string, signal?: AbortSignal) {
  return (
    await apiClient.get<ModelVersion>(
      controlPlaneURL(`/registry/versions/${id}/`),
      { signal },
    )
  ).data;
}
