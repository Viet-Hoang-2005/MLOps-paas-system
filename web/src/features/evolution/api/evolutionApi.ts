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

export interface SupplementalArtifactsPayload {
  source_code_file?: File | null;
  reference_data_file?: File | null;
  label_mapping_file?: File | null;
  input_schema_file?: File | null;
  metrics_file?: File | null;
  params_file?: File | null;
  model_insights_file?: File | null;
  feature_importance_file?: File | null;
}

export async function addSupplementalArtifacts(
  versionId: string,
  payload: SupplementalArtifactsPayload,
): Promise<ModelVersion> {
  const formData = new FormData();
  if (payload.source_code_file) {
    formData.append("source_code_file", payload.source_code_file);
  }
  if (payload.reference_data_file) {
    formData.append("reference_data_file", payload.reference_data_file);
  }
  if (payload.label_mapping_file) {
    formData.append("label_mapping_file", payload.label_mapping_file);
  }
  if (payload.input_schema_file) {
    formData.append("input_schema_file", payload.input_schema_file);
  }
  if (payload.metrics_file) {
    formData.append("metrics_file", payload.metrics_file);
  }
  if (payload.params_file) {
    formData.append("params_file", payload.params_file);
  }
  if (payload.model_insights_file) {
    formData.append("model_insights_file", payload.model_insights_file);
  }
  if (payload.feature_importance_file) {
    formData.append("feature_importance_file", payload.feature_importance_file);
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

