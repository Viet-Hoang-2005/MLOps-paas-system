import type { ResourceId } from '@/shared/types';

export type RegistryStage = 'none' | 'candidate' | 'staging' | 'production' | 'archived';
export type RegistrySourceType = 'manual_upload' | 'training_job' | 'imported';
export type RegistryHistoryStatus = 'success' | 'failed' | 'running';
export type RegistryDeployabilityStatus = 'unknown' | 'deployable' | 'track_only' | 'invalid';
export type RoutingAliasName = 'production' | 'latest' | 'champion';

export interface RegistryArtifactManifestItem {
  path: string;
  size_bytes?: number;
  sha256?: string;
  kind?: 'model' | 'checkpoint' | 'metadata' | 'log' | 'other' | string;
}

export interface RegistryModelInsightItem {
  name: string;
  value: number;
  abs_value?: number;
  class_name?: string;
  rank?: number;
}

export interface RegistryModelInsightsSummary {
  schema_version?: string;
  kind?: 'feature_importance' | 'coefficients' | string;
  source?: string;
  feature_count?: number;
  items?: RegistryModelInsightItem[];
}

export type DriftSummaryStatus = 'not_configured' | 'healthy' | 'drift_detected' | 'report_unavailable' | 'unknown';

export interface DriftSummary {
  configured: boolean;
  status: DriftSummaryStatus;
  drift_percent: number | null;
  driftPercent?: number | null;
  drift_score: number | null;
  driftScore?: number | null;
  dataset_drift: boolean | null;
  datasetDrift?: boolean | null;
  latest_result_id: number | null;
  latestResultId?: number | null;
  drift_job_id: number | null;
  driftJobId?: number | null;
  report_url: string | null;
  reportUrl?: string | null;
  report_page_url: string;
  reportPageUrl?: string;
  last_checked_at: string | null;
  lastCheckedAt?: string | null;
  drifted_features_count: number | null;
  driftedFeaturesCount?: number | null;
  total_features: number | null;
  totalFeatures?: number | null;
  message: string;
}

export interface RoutingAlias {
  alias_name: RoutingAliasName | string;
  aliasName?: RoutingAliasName | string;
  is_target: boolean;
  isTarget?: boolean;
  endpoint_url: string;
  endpointUrl?: string;
  status: string;
  promoted_at: string | null;
  promotedAt?: string | null;
  family_id?: ResourceId;
  familyId?: ResourceId;
  target_version_id?: ResourceId;
  targetVersionId?: ResourceId;
}

export interface PromoteAliasResponse {
  success: boolean;
  message: string;
  alias?: RoutingAlias;
  reason_code?: string;
  reasonCode?: string;
  warning?: string;
}

export interface RegistryVersion {
  id: ResourceId;
  project_id: ResourceId;
  tenant?: number | string;
  family?: number;
  version: string;
  source_training_job?: ResourceId | null;
  source_training_job_id?: ResourceId | null;
  source_training_job_name?: string;
  source_training_job_status?: string;
  source_training_job_backend?: string;
  source_type: RegistrySourceType;
  artifact_uri: string;
  image_name: string;
  endpoint_url: string;
  stage: RegistryStage;
  training_summary?: Record<string, unknown>;
  metrics_summary?: Record<string, unknown>;
  metricsSummary?: Record<string, unknown>;
  params_summary?: Record<string, unknown>;
  paramsSummary?: Record<string, unknown>;
  model_insights_summary?: RegistryModelInsightsSummary;
  modelInsightsSummary?: RegistryModelInsightsSummary;
  has_model_insights?: boolean;
  hasModelInsights?: boolean;
  model_insights_kind?: string;
  modelInsightsKind?: string;
  model_insights_item_count?: number;
  modelInsightsItemCount?: number;
  artifact_manifest?: RegistryArtifactManifestItem[];
  artifactManifest?: RegistryArtifactManifestItem[];
  tracking_status?: string;
  tracking_error?: string;
  tracking_ingested_at?: string | null;
  deployability_status?: RegistryDeployabilityStatus;
  deployability_reason?: string;
  primary_metrics?: Record<string, number>;
  can_build?: boolean;
  can_deploy?: boolean;
  routing_alias_enabled?: boolean;
  routingAliasEnabled?: boolean;
  can_promote?: boolean;
  canPromote?: boolean;
  routing_aliases?: RoutingAlias[];
  routingAliases?: RoutingAlias[];
  build_disabled_reason?: string;
  deploy_disabled_reason?: string;
  build_status?: string;
  build_error?: string;
  deployment_status?: string;
  endpoint_status?: string;
  endpoint_error?: string;
  endpoint_last_checked_at?: string | null;
  message?: string;
  reason_code?: string;
  technical_detail?: string;
  health?: Record<string, unknown>;
  mlflow_run_id?: string | null;
  mlflow_experiment_id?: string | null;
  mlflow_run_url?: string | null;
  mlflow_model_uri?: string | null;
  mlflow_artifact_uri?: string | null;
  created_at: string;
  updated_at: string;
  drift_summary?: DriftSummary;
  driftSummary?: DriftSummary;
}

export interface RegistrySmokeTestRequest {
  features: Record<string, unknown>;
}

export interface RegistrySmokeTestResponse {
  success: boolean;
  endpoint_url: string;
  status?: string;
  reason_code?: string;
  message?: string;
  technical_detail?: string;
  prediction?: unknown;
  confidence?: number | null;
  latency_ms?: number;
  status_code?: number;
  response?: unknown;
  error?: string;
}

export interface RegistryMetricDiff {
  name: string;
  left: unknown;
  right: unknown;
  delta: number | null;
  delta_percent: number | null;
  higher_is_better: boolean | null;
  winner: 'left' | 'right' | 'tie' | 'unknown';
}

export interface RegistryParamDiff {
  name: string;
  left: unknown;
  right: unknown;
  changed: boolean;
  only_in?: 'left' | 'right' | '';
}

export interface RegistryArtifactDiff {
  added: RegistryArtifactManifestItem[];
  removed: RegistryArtifactManifestItem[];
  changed: Array<{
    path: string;
    left_size_bytes?: number;
    right_size_bytes?: number;
    left_sha256?: string;
    right_sha256?: string;
    left_kind?: string;
    right_kind?: string;
  }>;
  unchanged_count: number;
}

export interface RegistryVersionCompareResponse {
  family: Pick<RegistryFamily, 'id' | 'name' | 'display_name'>;
  left: Partial<RegistryVersion> & Pick<RegistryVersion, 'id' | 'version' | 'stage'>;
  right: Partial<RegistryVersion> & Pick<RegistryVersion, 'id' | 'version' | 'stage'>;
  metrics_diff: RegistryMetricDiff[];
  params_diff: RegistryParamDiff[];
  artifact_diff: RegistryArtifactDiff;
  deployability_diff: {
    left: { status: string; reason: string };
    right: { status: string; reason: string };
  };
  deployment_diff: {
    left_stage: string;
    right_stage: string;
    left_endpoint_url: string;
    right_endpoint_url: string;
    left_deployed: boolean;
    right_deployed: boolean;
    left_image_name: string;
    right_image_name: string;
  };
  recommendation: {
    winner: 'left' | 'right' | 'unknown';
    confidence: 'low' | 'medium' | 'high';
    reason: string;
    warnings: string[];
  };
}

export interface RegistryFamily {
  id: ResourceId;
  tenant?: number | string;
  name: string;
  display_name: string;
  description: string;
  current_production_version: RegistryVersion | null;
  production_alias_version_id?: ResourceId | null;
  productionAliasVersionId?: ResourceId | null;
  latest_alias_version_id?: ResourceId | null;
  latestAliasVersionId?: ResourceId | null;
  champion_alias_version_id?: ResourceId | null;
  championAliasVersionId?: ResourceId | null;
  version_count?: number;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface RegistryMetric {
  id: ResourceId;
  metric_name: string;
  value: number;
  step: number;
  source: string;
  created_at: string;
  extra?: Record<string, unknown>;
}

export interface RegistryHistory {
  id: ResourceId;
  action: string;
  status: RegistryHistoryStatus;
  version: string;
  from_stage: string;
  to_stage: string;
  message: string;
  actor: string;
  created_at: string;
  extra?: Record<string, unknown>;
}
