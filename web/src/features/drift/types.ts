import type { ResourceId } from '@/shared/types';

export interface DriftMonitoringResult {
  id: ResourceId;
  status: string;
  report_html_uri: string;
  report_json_uri: string;
  summary_uri: string;
  drift_score: number | null;
  has_drift: boolean | null;
  summary: Record<string, unknown>;
  error_message: string;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
}

export interface DriftMonitoringJob {
  id: ResourceId;
  project_id: ResourceId;
  version_id: ResourceId;
  reference_asset_id: ResourceId;
  reference_asset_name: string;
  name: string;
  trigger_threshold: number;
  backend: string;
  is_active: boolean;
  runs: DriftMonitoringResult[];
  created_at: string;
  updated_at: string;
}

export interface WorkspaceDataFile {
  id: ResourceId;
  relative_path: string;
  s3_uri: string;
  download_url: string;
  size_bytes: number;
  updated_at: string;
}

export interface DriftMonitorInput {
  project_id: ResourceId;
  trigger_threshold: number;
  reference_data_s3_path: string;
}

export interface ProductionDataRecord {
  id: string;
  project_id: ResourceId;
  model_version_id: ResourceId;
  timestamp: string | null;
  features: Record<string, unknown>;
  prediction: string | null;
}
