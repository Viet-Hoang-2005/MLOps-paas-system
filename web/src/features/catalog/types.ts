import type { ResourceId } from "@/shared/types";

export type ModelAccessMode = "private" | "public";
export type ModelFlavor = "sklearn" | "xgboost" | "pytorch" | "tensorflow";
export type ModelArtifactFormat = "raw" | "archive";
export type RegistryDeployabilityStatus = "unknown" | "deployable" | "track_only" | "invalid";
export interface RegistryModelInsightsSummary {
  schema_version?: string;
  kind?: "feature_importance" | "coefficients" | string;
  source?: string;
  feature_count?: number;
  items?: Array<{ name: string; value: number; abs_value?: number; class_name?: string; rank?: number }>;
}
export type ModelDeletionState =
  "active" | "deleting" | "deleted" | "delete_failed";

export interface ActiveModelEndpoint {
  id: ResourceId;
  deployment_id: ResourceId;
  version_id: ResourceId;
  url: string;
  health_url: string;
  health_status: string;
  deployment_status: Deployment["status"];
  last_checked_at: string | null;
}

export interface ModelProject {
  id: ResourceId;
  name: string;
  description: string;
  access_mode: ModelAccessMode;
  is_active: boolean;
  deletion_state?: ModelDeletionState;
  deletion_error?: string;
  deleted_at?: string | null;
  endpoint_url?: string;
  active_endpoint?: ActiveModelEndpoint | null;
  flavor?: ModelFlavor | "";
  workflow_status?: "setup" | "image_ready" | "deployed";
  lifecycle_status?: "active" | "archived" | "deleted";
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
  aliases: string[];
  deployability: RegistryDeployabilityStatus;
  deployability_reason: string;
  metrics_summary: Record<string, unknown>;
  params_summary: Record<string, unknown>;
  insights_summary: RegistryModelInsightsSummary;
  artifacts: Array<{ id: ResourceId; kind: string; name: string; uri: string; checksum?: string }>;
  registered_at: string;
}

export interface Build {
  id: ResourceId;
  project_id: ResourceId;
  source_kind: "draft" | "model_version" | "training_job";
  source_draft_revision_id: ResourceId | null;
  source_version_id: ResourceId | null;
  source_job_id: ResourceId | null;
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
  id: ResourceId;
  project_id: ResourceId;
  version_id: ResourceId;
  build_id: ResourceId | null;
  target: "staging" | "production";
  backend: "docker" | "argo";
  status:
    "pending" | "deploying" | "healthy" | "unhealthy" | "failed" | "stopped";
  error_message: string;
}

export interface Endpoint {
  id: ResourceId;
  deployment_id: ResourceId;
  version_id: ResourceId;
  public_url: string;
  internal_url: string;
  health_status: string;
}

export interface ModelProjectFormValues {
  name: string;
  description: string;
  access_mode: ModelAccessMode;
  task_domain?: string;
}

export interface ProjectMetadataForm {
  name: string;
  description: string;
  access_mode: ModelAccessMode;
}

export type ModelBuildInputAssetKind =
  | "model"
  | "reference_data"
  | "source_code"
  | "data_contract"
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

export interface ModelEndpointLogsResponse {
  project_id: ResourceId;
  container_name: string;
  logs: string;
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

export interface ReferenceSnapshotOverview {
  id: ResourceId;
  role: string;
  manifest_uri: string;
  manifest_checksum: string;
  schema_checksum: string;
  row_count: number;
}

export interface PresentOverview {
  has_production: boolean;
  is_live: boolean;
  version: string | null;
  version_id: ResourceId | null;
  image_uri: string;
  endpoint_url: string | null;
  health_status: string | null;
  reference_snapshot: ReferenceSnapshotOverview | null;
  metrics: Record<string, number | unknown>;
}

export interface DraftAssetOverview {
  id: ResourceId;
  kind: string;
  name: string;
  size_bytes: number;
  checksum: string;
  content_type: string;
  download_url: string;
  created_at: string;
  updated_at: string;
}

export interface DraftOverview {
  id: ResourceId;
  status: "editing" | "saving" | "ready" | "locked" | string;
  revision: number;
  saved_revision: number;
  flavor: string;
  artifact_format: string;
  requirements_snapshot: string;
  locked_by_build_id: ResourceId | null;
  saved_at: string | null;
  saved_snapshot_id: ResourceId | null;
  is_dirty: boolean;
  has_mandatory_assets: boolean;
  can_build: boolean;
  assets: DraftAssetOverview[];
}

export interface CandidateVersionOverview {
  id: ResourceId;
  version: string;
  registered_at: string;
  aliases: string[];
}

export interface ModelProjectOverviewResponse {
  project: {
    id: ResourceId;
    name: string;
    description: string;
    task_domain: string;
    access_mode: ModelAccessMode;
    lifecycle_status: string;
    created_at: string;
    updated_at: string;
  };
  present: PresentOverview;
  draft: DraftOverview;
  candidate_versions: CandidateVersionOverview[];
}
