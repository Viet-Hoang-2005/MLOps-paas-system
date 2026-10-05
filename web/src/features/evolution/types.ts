export type RegistryStage =
  "none" | "candidate" | "staging" | "production" | "archived";
export type RegistryDeployabilityStatus =
  "unknown" | "deployable" | "track_only" | "invalid";

export interface RegistryModelInsightItem {
  name: string;
  value: number;
  abs_value?: number;
  class_name?: string;
  rank?: number;
}

export interface RegistryModelInsightsSummary {
  schema_version?: string;
  kind?: "feature_importance" | "coefficients" | string;
  source?: string;
  feature_count?: number;
  items?: RegistryModelInsightItem[];
}

export interface VersionArtifact {
  id: string;
  kind: string;
  name: string;
  uri: string;
  checksum: string;
  size_bytes: number;
  content_type: string;
  metadata: Record<string, unknown>;
  created_at: string;
}

export interface VersionMetric {
  id: string;
  name: string;
  value: number;
  step: number | null;
  timestamp: string | null;
  metadata: Record<string, unknown>;
}

export interface VersionEvent {
  id: string;
  event_type: string;
  from_state: string;
  to_state: string;
  metadata: Record<string, unknown>;
  created_at: string;
}
