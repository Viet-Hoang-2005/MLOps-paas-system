import type { ResourceId } from '@/shared/types';
import type {
  RegistryDeployabilityStatus,
  RegistryModelInsightsSummary,
  RegistryStage,
} from '@/features/registry/types';

export type ModelAccessMode = 'private' | 'public';
export type ModelProjectStatus =
  | 'registered'
  | 'ready'
  | 'uploading'
  | 'deploying'
  | 'deployed'
  | 'unhealthy'
  | 'deploy_failed'
  | 'stopped'
  | 'archived'
  | 'error'
  | 'disabled';
export type ModelBuildStatus = 'not_started' | 'pending' | 'queued' | 'building' | 'ready' | 'failed' | 'cancelled' | 'error';
export type ModelEndpointStatus = 'not_deployed' | 'deploying' | 'healthy' | 'unhealthy' | 'deploy_failed' | 'stopped';
export type ModelFlavor = 'sklearn' | 'xgboost' | 'pytorch' | 'tensorflow';
export type ModelArtifactFormat = 'raw' | 'mlflow_zip';
export type ModelSourceType = 'manual_upload' | 'training_job';
export type ModelLifecycleStatus = 'metadata' | 'image_ready' | 'deployed';
export type ModelDeletionState = 'active' | 'deleting' | 'deleted' | 'delete_failed';

export interface ActiveModelEndpoint {
  id: ResourceId;
  deployment_id: ResourceId;
  version_id: ResourceId;
  url: string;
  health_url: string;
  health_status: string;
  deployment_status: Deployment['status'];
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
  version?: string;
  source_type?: ModelSourceType;
  source_training_job?: ResourceId | null;
  source_artifact_uri?: string;
  model_uri?: string;
  endpoint_url?: string;
  active_endpoint?: ActiveModelEndpoint | null;
  health_url?: string;
  status?: ModelProjectStatus;
  error_message?: string;
  endpoint_status?: ModelEndpointStatus;
  endpoint_error?: string;
  endpoint_last_checked_at?: string | null;
  endpoint_container_name?: string;
  endpoint_image_name?: string;
  endpoint_public_path?: string;
  endpoint_internal_path?: string;
  source_artifact?: string;
  flavor?: ModelFlavor | '';
  package_manifest?: Record<string, unknown>;
  package_preview_tree?: string[];
  build_status?: ModelBuildStatus;
  lifecycle_status?: ModelLifecycleStatus;
  build_id?: ResourceId;
  build_error?: string;
  deployment_id?: ResourceId;
  metrics_summary?: Record<string, unknown>;
  params_summary?: Record<string, unknown>;
  model_insights_summary?: RegistryModelInsightsSummary;
  has_model_insights?: boolean;
  metadata_warnings?: string[];
  source_code_file?: string | null;
  reference_data_file?: string | null;
  source_code?: ProjectAssetSummary | null;
  reference_data?: ProjectAssetSummary | null;
  created_at: string;
  updated_at: string;
}

export interface ModelProjectListResponse { models: ModelProject[] }

export interface ModelVersion {
  id: ResourceId;
  project_id: ResourceId;
  version: string;
  source_job_id: ResourceId | null;
  requirements_snapshot: string;
  flavor: ModelFlavor | '';
  stage: RegistryStage;
  deployability: RegistryDeployabilityStatus;
  deployability_reason: string;
  metrics_summary: Record<string, unknown>;
  params_summary: Record<string, unknown>;
  insights_summary: RegistryModelInsightsSummary;
  artifacts: Array<{ id: ResourceId; kind: string; name: string; uri: string }>;
  registered_at: string;
}

export interface Build {
  id: ResourceId;
  project_id: ResourceId;
  version_id: ResourceId | null;
  version_number: string | null;
  flavor: ModelFlavor;
  artifact_format: ModelArtifactFormat;
  requirements_snapshot: string;
  backend: 'docker' | 'argo';
  status: 'pending' | 'queued' | 'building' | 'ready' | 'failed' | 'cancelled';
  image_uri: string;
  image_digest: string;
  package_uri: string;
  input_assets: BuildInputAssetSummary[];
  logs: string;
  error_message: string;
}

export interface Deployment {
  id: ResourceId;
  version_id: ResourceId;
  build_id: ResourceId;
  backend: 'docker' | 'argo';
  status: 'pending' | 'deploying' | 'healthy' | 'unhealthy' | 'failed' | 'stopped';
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
  version?: string;
  artifact?: File | null;
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

export type ModelBuildFormValues = ProjectMetadataForm & BuildInputForm;

export type ModelBuildInputAssetKind =
  | 'source_artifact'
  | 'label_mapping'
  | 'metrics'
  | 'params'
  | 'model_insights'
  | 'feature_importance'
  | 'input_schema';

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
