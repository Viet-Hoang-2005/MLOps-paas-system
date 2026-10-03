export type RegistryStage =
  | "none"
  | "candidate"
  | "staging"
  | "production"
  | "archived";
export type RegistryDeployabilityStatus =
  | "unknown"
  | "deployable"
  | "track_only"
  | "invalid";

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
