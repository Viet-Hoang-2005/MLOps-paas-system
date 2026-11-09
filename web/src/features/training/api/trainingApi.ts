import { apiClient } from "@/shared/api/client";
import { controlPlaneURL } from "@/shared/api/config";
import { fetchAllPages } from "@/shared/api/pagination";
import type {
  TrainingJob,
  TrainingJobDownloadURLResponse,
  TrainingJobDeletionRequest,
  TrainingJobEventsResponse,
  TrainingJobFormValues,
  TrainingJobListResponse,
  TrainingJobLogsResponse,
  TrainingJobMetricsResponse,
  TrainingJobModelOutputSummary,
  TrainingJobStatus,
  TrainingRuntimeCapabilities,
  TrainingUsageResponse,
  ReferenceDataPreview,
} from "@/features/training/types";

const trainingJobFormData = (payload: TrainingJobFormValues) => {
  const formData = new FormData();
  formData.append("name", payload.name);
  formData.append("model_flavor", payload.model_flavor);
  formData.append("project", payload.project_id || "");
  formData.append("entry_point", payload.entry_point || "train.py");
  formData.append("requirements_text", payload.requirements_text);
  formData.append("vcpu", String(payload.vcpu));
  formData.append("memory_mb", String(payload.memory));
  formData.append("max_runtime_seconds", String(payload.max_runtime_seconds));
  formData.append("accelerator_type", payload.accelerator_type);
  formData.append("accelerator_count", String(payload.accelerator_count));
  formData.append("accelerator_model", payload.accelerator_model);
  formData.append("local_gpu_id", payload.local_gpu_id);
  if (payload.source_zip) formData.append("source_zip", payload.source_zip);
  if (payload.training_data)
    formData.append("training_data", payload.training_data);
  return formData;
};

export const createTrainingJob = async (
  payload: TrainingJobFormValues,
): Promise<TrainingJob> => {
  const { data: job } = await apiClient.post<TrainingJob>(
    controlPlaneURL("/training-jobs/"),
    trainingJobFormData(payload),
    { headers: { "Content-Type": "multipart/form-data" } },
  );
  return (
    await apiClient.post<TrainingJob>(
      controlPlaneURL(`/training-jobs/${job.id}/submit/`),
    )
  ).data;
};

export const listTrainingJobs = async (): Promise<TrainingJobListResponse> => {
  const data = await fetchAllPages<TrainingJob>(
    controlPlaneURL("/training-jobs/"),
  );
  return { training_jobs: data };
};

export const getTrainingUsage = async (): Promise<TrainingUsageResponse> => {
  return (await apiClient.get<TrainingUsageResponse>(controlPlaneURL("/training-jobs/usage/"))).data;
};

export const getTrainingJob = async (jobId: string): Promise<TrainingJob> =>
  (
    await apiClient.get<TrainingJob>(
      controlPlaneURL(`/training-jobs/${jobId}/`),
    )
  ).data;

export const refreshTrainingJobStatus = getTrainingJob;

export const getTrainingJobDownloadUrl = async (
  jobId: string,
): Promise<TrainingJobDownloadURLResponse> =>
  (
    await apiClient.get<TrainingJobDownloadURLResponse>(
      controlPlaneURL(`/training-jobs/${jobId}/download/`),
    )
  ).data;

export const deleteTrainingOutputs = async (
  jobId: string,
): Promise<TrainingJob> =>
  (
    await apiClient.delete<TrainingJob>(
      controlPlaneURL(`/training-jobs/${jobId}/outputs/`),
    )
  ).data;

export const getTrainingRuntimeCapabilities =
  async (refresh = false): Promise<TrainingRuntimeCapabilities> =>
    (
      await apiClient.get<TrainingRuntimeCapabilities>(
        controlPlaneURL("/training-jobs/runtime-capabilities/"),
        { params: refresh ? { refresh: "1" } : undefined },
      )
    ).data;

export const getTrainingJobLogs = async (
  jobId: string,
  offset = 0,
): Promise<TrainingJobLogsResponse> => {
  const { data } = await apiClient.get<{
    training_job_id: string;
    logs: string[];
    next_offset: number;
    status: TrainingJobStatus;
    error_message: string;
  }>(controlPlaneURL(`/training-jobs/${jobId}/logs/`), { params: { offset } });
  return {
    job_id: data.training_job_id,
    training_job_id: data.training_job_id,
    status: data.status,
    logs: data.logs,
    text: data.logs.join("\n"),
    next_offset: data.next_offset,
    error_message: data.error_message,
  };
};

export const getTrainingJobMetrics = async (
  jobId: string,
): Promise<TrainingJobMetricsResponse> => {
  return (await apiClient.get<TrainingJobMetricsResponse>(
    controlPlaneURL(`/training-jobs/${jobId}/runtime-metrics/`),
  )).data;
};

export const getTrainingJobEvents = async (
  jobId: string,
): Promise<TrainingJobEventsResponse> => ({
  events: (
    await apiClient.get<TrainingJobEventsResponse["events"]>(
      controlPlaneURL(`/training-jobs/${jobId}/events/`),
    )
  ).data,
});

export const cancelTrainingJob = async (
  jobId: string,
): Promise<TrainingJob> => {
  const { data } = await apiClient.post<
    TrainingJob | { training_job: TrainingJob }
  >(controlPlaneURL(`/training-jobs/${jobId}/cancel/`));
  return "training_job" in data ? data.training_job : data;
};

export const retryTrainingJob = async (jobId: string): Promise<TrainingJob> =>
  (
    await apiClient.post<TrainingJob>(
      controlPlaneURL(`/training-jobs/${jobId}/retry/`),
    )
  ).data;

export const deleteTrainingJob = async (
  jobId: string,
): Promise<TrainingJobDeletionRequest> =>
  (
    await apiClient.delete<TrainingJobDeletionRequest>(
      controlPlaneURL(`/training-jobs/${jobId}/`),
    )
  ).data;

export const getModelOutputSummary = async (
  jobId: string,
): Promise<TrainingJobModelOutputSummary> =>
  (
    await apiClient.get<TrainingJobModelOutputSummary>(
      controlPlaneURL(`/training-jobs/${jobId}/model-output/`),
    )
  ).data;

export const patchModelOutput = async (
  jobId: string,
  payload: {
    output_revision: number;
    source_code_file?: File | null;
    reference_data_file?: File | null;
    label_mapping_file?: File | null;
    input_schema_file?: File | null;
    build_requirements_text?: string;
    remove_assets?: string[];
  },
): Promise<TrainingJobModelOutputSummary> => {
  const formData = new FormData();
  formData.append("output_revision", String(payload.output_revision));
  if (payload.label_mapping_file) formData.append("label_mapping_file", payload.label_mapping_file);
  if (payload.input_schema_file) formData.append("input_schema_file", payload.input_schema_file);
  if (payload.build_requirements_text !== undefined) formData.append("build_requirements_text", payload.build_requirements_text);
  if (payload.source_code_file) {
    formData.append("source_code_file", payload.source_code_file);
  }
  if (payload.reference_data_file) {
    formData.append("reference_data_file", payload.reference_data_file);
  }
  if (payload.remove_assets && payload.remove_assets.length > 0) {
    formData.append("remove_assets", JSON.stringify(payload.remove_assets));
  }
  return (
    await apiClient.patch<TrainingJobModelOutputSummary>(
      controlPlaneURL(`/training-jobs/${jobId}/model-output/`),
      formData,
      { headers: { "Content-Type": "multipart/form-data" } },
    )
  ).data;
};

export const getJobReferencePreview = async (
  jobId: string,
): Promise<ReferenceDataPreview> =>
  (
    await apiClient.get<ReferenceDataPreview>(
      controlPlaneURL(`/training-jobs/${jobId}/reference-preview/`),
    )
  ).data;

export const getTrainingJobExperimentMetrics = async (
  jobId: string,
): Promise<import("@/features/training/types").TrainingJobExperimentMetricsResponse> =>
  (
    await apiClient.get<import("@/features/training/types").TrainingJobExperimentMetricsResponse>(
      controlPlaneURL(`/training-jobs/${jobId}/experiment-metrics/`),
    )
  ).data;

export const compareTrainingRuns = async (
  jobIds: string[],
): Promise<import("@/features/training/types").TrainingRunsCompareResponse> =>
  (
    await apiClient.get<import("@/features/training/types").TrainingRunsCompareResponse>(
      controlPlaneURL(`/training-jobs/compare/?job_ids=${jobIds.join(",")}`),
    )
  ).data;

