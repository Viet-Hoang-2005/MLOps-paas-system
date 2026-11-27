import { apiClient } from "@/shared/api/client";
import { inferenceClient } from "@/shared/api/inferenceClient";
import { controlPlaneURL } from "@/shared/api/config";
import { fetchAllPages } from "@/shared/api/pagination";
import type { MessageResponse } from "@/shared/types";
import type {
  ModelPredictionResponse,
  ModelProject,
  ModelProjectFormValues,
  ModelProjectListResponse,
  ModelVersion,
} from "@/features/projects/types";

const toModelProject = (project: ModelProject): ModelProject => {
  const endpoint = project.active_endpoint;
  const endpointStatus =
    endpoint?.deployment_status === "deploying" ||
    endpoint?.deployment_status === "pending"
      ? "deploying"
      : endpoint?.deployment_status === "stopped"
        ? "stopped"
        : endpoint?.deployment_status === "failed"
          ? "deploy_failed"
          : endpoint?.deployment_status === "succeeded"
            ? endpoint.health_status
            : endpoint
              ? "unknown"
              : "not_deployed";
  return {
    ...project,
    version: endpoint?.version_number,
    endpoint_url: endpoint?.url ?? "",
    health_url: endpoint?.health_url ?? "",
    endpoint_status: endpointStatus,
    deployment_id: endpoint?.deployment_id,
    endpoint_last_checked_at: endpoint?.last_checked_at ?? null,
  };
};

export const listModelProjects =
  async (): Promise<ModelProjectListResponse> => {
    const data = await fetchAllPages<ModelProject>(controlPlaneURL("/models/"));
    return {
      models: data.map(toModelProject),
    };
  };

export const getModelProject = async (modelId: string): Promise<ModelProject> =>
  toModelProject(
    (await apiClient.get<ModelProject>(controlPlaneURL(`/models/${modelId}/`)))
      .data,
  );

export const getVersionSnapshot = async (
  versionId: string,
): Promise<ModelVersion> =>
  (
    await apiClient.get<ModelVersion>(
      controlPlaneURL(`/registry/versions/${versionId}/`),
    )
  ).data;

export const getRunningSource = async (
  id: string,
  versionId?: string,
): Promise<string> => {
  const query = versionId ? `?version_id=${encodeURIComponent(versionId)}` : "";
  return (
    await apiClient.get<{ content: string }>(
      controlPlaneURL(`/models/${id}/running-source/${query}`),
    )
  ).data.content;
};

export const updateModelProject = async (
  modelId: string,
  payload: ModelProjectFormValues,
): Promise<ModelProject> =>
  (
    await apiClient.put<ModelProject>(controlPlaneURL(`/models/${modelId}/`), {
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
  (
    await inferenceClient.post<ModelPredictionResponse>(endpointUrl, {
      features,
    })
  ).data;

export interface ModelInsightItem {
  name: string;
  value: number;
  abs_value?: number;
  class_name?: string;
  rank?: number;
}

export interface ModelInsightsSummary {
  schema_version?: string;
  kind?: string;
  source?: string;
  feature_count?: number;
  items?: ModelInsightItem[];
}

export interface ModelLabelMappingData {
  filename: string;
  mapping: Record<string, unknown> | unknown[];
}

export interface ModelInputSchemaData {
  filename: string;
  schema: unknown;
}

export interface ModelArtifactSummary {
  kind: string;
  name: string;
  size_bytes: number;
}

export interface ModelAttributesResponse {
  metrics: Record<string, unknown> | null;
  params: Record<string, unknown> | null;
  insights: ModelInsightsSummary | null;
  model_insights?: ModelInsightsSummary | null;
  feature_importance?: ModelInsightsSummary | null;
  label_mapping: ModelLabelMappingData | null;
  input_schema: ModelInputSchemaData | null;
  artifacts: ModelArtifactSummary[];
  summary_sources?: {
    metrics: Record<string, "registered" | "supplemental">;
    params: Record<string, "registered" | "supplemental">;
    model_insights?: "registered" | "supplemental" | null;
    feature_importance?: "registered" | "supplemental" | null;
  };
  supplemental_summaries?: Record<string, unknown>;
}

export const getPreviewAttributes = async (
  modelId: string,
): Promise<ModelAttributesResponse> =>
  (
    await apiClient.get<ModelAttributesResponse>(
      controlPlaneURL(`/models/${modelId}/preview/attributes/`),
    )
  ).data;

export const getRunningAttributes = async (
  modelId: string,
  versionId?: string,
): Promise<ModelAttributesResponse> => {
  const query = versionId ? `?version_id=${encodeURIComponent(versionId)}` : "";
  return (
    await apiClient.get<ModelAttributesResponse>(
      controlPlaneURL(`/models/${modelId}/running-attributes/${query}`),
    )
  ).data;
};

export const getRunningLabelMapping = async (
  modelId: string,
  versionId?: string,
): Promise<ModelLabelMappingData> => {
  const query = versionId ? `?version_id=${encodeURIComponent(versionId)}` : "";
  return (
    await apiClient.get<ModelLabelMappingData>(
      controlPlaneURL(`/models/${modelId}/label-mapping/${query}`),
    )
  ).data;
};
