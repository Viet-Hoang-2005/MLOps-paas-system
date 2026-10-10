import type { ResourceId } from "@/shared/types";

export interface DriftMonitoringResult {
  observation_status?: "ok" | "retrying" | "cleanup_pending";
  observation_error?: string;
  execution_deadline_at?: string | null;
  runtime_started_at?: string | null;
  id: ResourceId;
  status: string;
  report_html_uri: string;
  report_json_uri: string;
  summary_uri: string;
  production_records?: number | null;
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
  reference_name: string;
  name: string;
  trigger_threshold: number;
  backend: string;
  is_active: boolean;
  runs: DriftMonitoringResult[];
  created_at: string;
  updated_at: string;
}

export interface DriftMonitorInput {
  project_id: ResourceId;
  trigger_threshold: number;
  version_id: ResourceId;
  reference_file?: File | null;
}

export interface ProductionDataRecord {
  id: string;
  project_id: ResourceId;
  model_version_id: ResourceId;
  timestamp: string | null;
  features: Record<string, unknown>;
  prediction: string | null;
}

export interface DriftDistribution {
  small_distribution?: {
    x: (string | number)[];
    y: number[];
  };
}

export interface DriftColumnReport {
  column_name: string;
  column_type: "num" | "cat" | string;
  stattest_name: string;
  stattest_threshold: number;
  drift_score: number;
  drift_detected: boolean;
  current?: DriftDistribution;
  reference?: DriftDistribution;
}

export interface DriftReportData {
  run_id: string;
  monitor_id: string;
  project_id: string;
  project_name: string;
  version: string;
  status: string;
  created_at: string | null;
  dataset_drift: boolean;
  drift_share: number;
  drift_score: number;
  number_of_columns: number;
  number_of_drifted_columns: number;
  production_records: number;
  data_quality?: {
    status?: string;
    missing_features_count?: number;
    extra_features_count?: number;
    high_null_features?: string[];
    [key: string]: unknown;
  };
  columns: DriftColumnReport[];
  artifacts: {
    html_url: string | null;
    json_url: string | null;
  };
}

