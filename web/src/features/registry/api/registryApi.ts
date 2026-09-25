import { apiClient } from "@/shared/api/client";
import { controlPlaneURL } from "@/shared/api/config";

export const rebuildRegistryVersion = async (
  versionId: string,
): Promise<{ id: string }> =>
  (
    await apiClient.post<{ id: string }>(
      controlPlaneURL(`/registry/versions/${versionId}/rebuild/`),
      {},
    )
  ).data;
