import { apiClient } from "@/shared/api/client";
import { controlPlaneURL } from "@/shared/api/config";
import type { ModelVersion } from "@/features/projects/types";
import type { ReferenceDataPreview } from "@/features/training/types";

export async function getVersionDetail(id: string, signal?: AbortSignal) {
  return (
    await apiClient.get<ModelVersion>(
      controlPlaneURL(`/registry/versions/${id}/`),
      { signal },
    )
  ).data;
}

export async function addSupplementalArtifacts(
  versionId: string,
  payload: {
    source_code_file?: File | null;
    reference_data_file?: File | null;
  },
): Promise<ModelVersion> {
  const formData = new FormData();
  if (payload.source_code_file) {
    formData.append("source_code_file", payload.source_code_file);
  }
  if (payload.reference_data_file) {
    formData.append("reference_data_file", payload.reference_data_file);
  }
  return (
    await apiClient.post<ModelVersion>(
      controlPlaneURL(`/registry/versions/${versionId}/supplemental-artifacts/`),
      formData,
      { headers: { "Content-Type": "multipart/form-data" } },
    )
  ).data;
}

export async function getVersionReferencePreview(
  versionId: string,
): Promise<ReferenceDataPreview> {
  return (
    await apiClient.get<ReferenceDataPreview>(
      controlPlaneURL(`/registry/versions/${versionId}/reference-preview/`),
    )
  ).data;
}

