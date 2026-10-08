import type { ResourceId } from "@/shared/types";
import type {
  RegistryDeployabilityStatus,
  RegistryModelInsightsSummary,
  RegistryStage,
  VersionArtifact,
  VersionMetric,
  VersionEvent,
} from "@/features/evolution/types";

export type ModelAccessMode = "private" | "public";
export type ApiHealthStatus = "unknown" | "healthy" | "unhealthy";
export type ModelEndpointStatus =
  | "not_deployed"
  | "deploying"
  | "healthy"
  | "unhealthy"
  | "unknown"
  | "deploy_failed"
  | "stopped";
export type ModelFlavor = "sklearn" | "xgboost" | "pytorch" | "tensorflow";
export type ModelArtifactFormat = "raw" | "mlflow_zip";
export type ModelLifecycleStatus = "preview" | "registered" | "running";
export type ModelDeletionState =
  "active" | "deleting" | "deleted" | "delete_failed";

export interface ActiveModelEndpoint {
  id: ResourceId;
  deployment_id: ResourceId;
  version_id: ResourceId;
  version_number: string;
  url: string;
  health_url: string;
  health_status: ApiHealthStatus;
  deployment_status: Deployment["status"];
  registration_status: Build["registration_status"];
  last_checked_at: string | null;
}

export interface ModelProject {
  preview_revision: number;
  preview_changed: boolean;
  id: ResourceId;
  name: string;
  description: string;
  access_mode: ModelAccessMode;
  is_active: boolean;
  deletion_state?: ModelDeletionState;
  deletion_error?: string;
  deleted_at?: string | null;
  version?: string;
  endpoint_url?: string;
  active_endpoint?: ActiveModelEndpoint | null;
  health_url?: string;
  endpoint_status?: ModelEndpointStatus;
  endpoint_last_checked_at?: string | null;
  flavor?: ModelFlavor | "";
  lifecycle_status?: ModelLifecycleStatus;
  latest_version_id?: ResourceId | null;
  deployment_id?: ResourceId;
  source_code?: ProjectAssetSummary | null;
  reference_data?: ProjectAssetSummary | null;
  created_at: string;
  updated_at: string;
}

export interface ModelProjectListResponse {
  models: ModelProject[];
}

export interface ModelVersion {
  id: ResourceId;
  project_id: ResourceId;
  version: string;
  source_job_id: ResourceId | null;
  requirements_snapshot: string;
  flavor: ModelFlavor | "";
  stage: RegistryStage;
  deployability: RegistryDeployabilityStatus;
  deployability_reason: string;
  metrics_summary: Record<string, unknown>;
  params_summary: Record<string, unknown>;
  insights_summary: RegistryModelInsightsSummary;
  supplemental_summaries?: Record<string, {
    value: unknown;
    uploaded_by: string | null;
    uploaded_at: string | null;
  }>;
  artifacts: VersionArtifact[];
  metrics: VersionMetric[];
  events: VersionEvent[];
  registered_at: string;
}

export interface Build {
  source_job_id?: ResourceId | null;
  created_at: string;
  preview_revision: number | null;
  registration_status: "unregistered" | "registering" | "registered" | "failed";
  registration_error: string;
  deletion_state: "active" | "deleting" | "delete_failed";
  deletion_error: string;
  id: ResourceId;
  project_id: ResourceId;
  version_id: ResourceId | null;
  version_number: string | null;
  flavor: ModelFlavor;
  artifact_format: ModelArtifactFormat;
  requirements_snapshot: string;
  backend: "docker" | "argo";
  status: "pending" | "queued" | "building" | "ready" | "failed" | "cancelled";
  image_uri: string;
  image_digest: string;
  package_uri: string;
  input_assets: BuildInputAssetSummary[];
  logs: string;
  error_message: string;
}

export interface Deployment {
  deployed_at?: string | null;
  id: ResourceId;
  version_id: ResourceId;
  build_id: ResourceId;
  backend: "docker" | "argo";
  status:
    | "pending"
    | "deploying"
    | "succeeded"
    | "failed"
    | "stopped"
    | "unconfirmed";
  error_message: string;
}

export interface Endpoint {
  id: ResourceId;
  deployment_id: ResourceId;
  version_id: ResourceId;
  public_url: string;
  internal_url: string;
  health_status: ApiHealthStatus;
}

export interface ModelProjectFormValues {
  name: string;
  description: string;
  access_mode: ModelAccessMode;
  source_code_file?: File | null;
  reference_data_file?: File | null;
}

export interface ProjectAssetSummary {
  name: string;
  download_url: string;
  checksum: string;
  size_bytes: number;
  content_type: string;
}

export interface ProjectMetadataForm {
  name: string;
  description: string;
  access_mode: ModelAccessMode;
  source_code_file: File | null;
  reference_data_file: File | null;
}

export interface CodeDataForm {
  source_code_file: File | null;
  reference_data_file: File | null;
}

export interface BuildInputForm {
  source_artifact: File | null;
  artifact_format: ModelArtifactFormat;
  label_mapping_file?: File | null;
  metrics_file?: File | null;
  params_file?: File | null;
  model_insights_file?: File | null;
  feature_importance_file?: File | null;
  input_schema_file?: File | null;
  flavor: ModelFlavor;
  requirements_text: string;
  requirements_file?: File | null;
}

export type ModelBuildFormValues = ProjectMetadataForm &
  CodeDataForm &
  BuildInputForm;

export type ModelBuildInputAssetKind =
  | "source_artifact"
  | "source_code"
  | "reference_data"
  | "training_output"
  | "label_mapping"
  | "metrics"
  | "params"
  | "model_insights"
  | "feature_importance"
  | "input_schema";

export interface BuildInputAssetSummary {
  id: ResourceId;
  kind: ModelBuildInputAssetKind;
  name: string;
  checksum: string;
  size_bytes: number;
  content_type: string;
  purged_at: string | null;
}

export interface ModelPredictionResponse {
  success: boolean;
  prediction_id?: string;
  id?: string;
  prediction: unknown;
  confidence: number | null;
  tenant_id: ResourceId;
  model_version_id: ResourceId;
}
