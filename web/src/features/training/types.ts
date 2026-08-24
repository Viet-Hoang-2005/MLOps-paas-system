import type { ResourceId } from '@/shared/types';
import type { ModelFlavor } from '@/features/catalog/types';

export type TrainingJobStatus =
  | 'pending'
  | 'queued'
  | 'uploading'
  | 'running'
  | 'cancelling'
  | 'completed'
  | 'failed'
  | 'cancelled';
export type TrainingAcceleratorType = 'none' | 'gpu';
export type TrainingModelStatus = 'none' | 'trained' | 'built' | 'deployed';

export interface TrainingBuild {
  id: ResourceId;
  project_id: ResourceId;
  source_job_id: ResourceId;
  version_id: ResourceId | null;
  version_number: string | null;
  flavor: ModelFlavor;
  status: 'pending' | 'queued' | 'building' | 'ready' | 'failed' | 'cancelled';
  image_uri: string;
  image_digest: string;
  error_message: string;
  created_at: string;
  updated_at: string;
}

export interface TrainingOutput {
  id: ResourceId;
  kind: 'model' | 'metric' | 'insight' | 'file';
  relative_path: string;
  s3_uri: string;
  checksum: string;
  size_bytes: number;
  content_type: string;
  metadata: Record<string, unknown>;
  created_at: string;
}

export interface TrainingJob {
  id: ResourceId;
  project_id: ResourceId;
  name: string;
  model_flavor: ModelFlavor;
  model_version: string;
  entry_point: string;
  requirements_text: string;
  training_backend: 'kubeflow' | 'local';
  backend: 'docker' | 'argo' | 'kubeflow' | 'local';
  vcpu: number;
  memory: number;
  memory_mb: number;
  max_runtime_seconds: number;
  accelerator_type: TrainingAcceleratorType;
  accelerator_count: number;
  source_zip: string;
  requirements_file: string;
  training_data: string;
  s3_source_uri: string;
  s3_training_data_uri: string;
  code_snapshot_uri: string;
  data_snapshot_uri: string;
  sagemaker_job_name: string;
  external_job_id: string;
  output_s3_uri: string;
  output_uri: string;
  model_artifact_uri: string;
  status: TrainingJobStatus;
  error_message: string;
  training_logs: string;
  tracking: Record<string, unknown>;
  started_at: string | null;
  completed_at: string | null;
  runtime_seconds: number;
  outputs: TrainingOutput[];
  outputs_purged_at: string | null;
  output_available: boolean;
  registration_build: TrainingBuild | null;
  model_status: TrainingModelStatus;
  stop_reason: string;
  retry_of: ResourceId | null;
  deletion_requested_at: string | null;
  deletion_error: string;
  deletion_pending: boolean;
  created_at: string;
  updated_at: string;
}

export interface TrainingJobListResponse { training_jobs: TrainingJob[] }

export interface TrainingJobDeletionRequest {
  id: ResourceId;
  status: TrainingJobStatus;
  deletion_pending: true;
  deletion_requested_at: string;
  deletion_error: string;
}

export interface TrainingJobFormValues {
  name: string;
  model_version?: string;
  model_flavor: ModelFlavor;
  entry_point: string;
  requirements_text: string;
  vcpu: number;
  memory: number;
  max_runtime_seconds: number;
  accelerator_type: TrainingAcceleratorType;
  accelerator_count: number;
  source_zip: File | null;
  training_data: File | null;
  project_id?: ResourceId;
}

export interface TrainingRuntimeCapabilities {
  enabled: boolean;
  backend: 'docker' | 'argo';
  cpu_profiles: Array<{ id: string; vcpu: number; memory_mb: number }>;
  accelerators: Array<{ type: TrainingAcceleratorType; counts: number[] }>;
}

export interface TrainingJobDownloadURLResponse { download_url: string }

export interface TrainingJobLogsResponse {
  job_id: ResourceId;
  training_job_id: ResourceId;
  status: TrainingJobStatus;
  logs: string | string[];
  text: string;
  log_stream_name?: string;
  next_token?: string;
  next_offset?: number;
  error_message?: string;
  updated_at?: string;
}

export interface TrainingMetricPoint {
  timestamp: string;
  cpu_percent: number | null;
  cpu_limit_cores: number | null;
  memory_used_mb: number | null;
  memory_limit_mb: number | null;
  memory_percent: number | null;
  gpu_available: boolean;
  gpu_percent: number | null;
  gpu_memory_used_mb: number | null;
  gpu_memory_total_mb: number | null;
  gpu_memory_percent: number | null;
}

export interface TrainingJobMetricsResponse {
  job_id: ResourceId;
  training_job_id: ResourceId;
  status: TrainingJobStatus;
  metrics_available: boolean;
  latest: TrainingMetricPoint | null;
  history: TrainingMetricPoint[];
  log_stream_name: string;
  message: string;
  updated_at: string;
}

export interface TrainingJobEvent {
  id: ResourceId;
  training_job?: ResourceId;
  event_type: string;
  message: string;
  metadata: Record<string, unknown>;
  created_at: string;
}

export interface TrainingJobEventsResponse { events: TrainingJobEvent[] }

export interface TrainingUsageResponse {
  training_backend: 'kubeflow' | 'local';
  monthly_quota_seconds: number;
  monthly_runtime_seconds: number;
  remaining_seconds: number;
  active_jobs_count: number;
  running_jobs_count: number;
  completed_jobs_count: number;
  failed_jobs_count: number;
  current_month_start: string;
  current_month_end: string;
}
