import { useOutletContext } from "react-router-dom";

import type {
  TrainingJob,
  TrainingJobEventsResponse,
  TrainingJobMetricsResponse,
  TrainingJobStatus,
} from "@/features/training/types";

export type TrainingJobDetailSection =
  "overview" | "logs" | "metrics" | "artifacts" | "config";

export interface TrainingJobDetailContextValue {
  job: TrainingJob;
  statusLabels: Record<TrainingJobStatus, string>;
  activeStatuses: TrainingJobStatus[];
  metrics?: TrainingJobMetricsResponse;
  loadingMetrics: boolean;
  eventsResponse?: TrainingJobEventsResponse;
  refreshingSection: "header" | "logs" | "metrics" | null;
  refreshLogs: () => Promise<void>;
  refreshMetrics: () => Promise<void>;
  refreshJob: () => Promise<void>;
  downloadOutput: () => void;
  downloadingOutput: boolean;
  requestDeleteOutputs: () => void;
  copyUri: (value: string) => void;
}

export function useTrainingJobDetailContext() {
  return useOutletContext<TrainingJobDetailContextValue>();
}
