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
  const { training_jobs: jobs } = await listTrainingJobs();
  const monthlyRuntime = jobs.reduce(
    (total, job) => total + job.runtime_seconds,
    0,
  );
  const trainingBackend = ["argo", "kubeflow"].includes(jobs[0]?.backend ?? "")
    ? "kubeflow"
    : "local";
  return {
    training_backend: trainingBackend,
    monthly_quota_seconds: 0,
    monthly_runtime_seconds: monthlyRuntime,
    remaining_seconds: 0,
    active_jobs_count: jobs.filter((job) =>
      ["pending", "queued", "uploading", "running", "cancelling"].includes(
        job.status,
      ),
    ).length,
    running_jobs_count: jobs.filter((job) => job.status === "running").length,
    completed_jobs_count: jobs.filter((job) => job.status === "completed")
      .length,
    failed_jobs_count: jobs.filter((job) => job.status === "failed").length,
    current_month_start: "",
    current_month_end: "",
  };
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
  async (): Promise<TrainingRuntimeCapabilities> =>
    (
      await apiClient.get<TrainingRuntimeCapabilities>(
        controlPlaneURL("/training-jobs/runtime-capabilities/"),
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
  const job = await getTrainingJob(jobId);
  return {
    job_id: job.id,
    training_job_id: job.id,
    status: job.status,
    metrics_available: false,
    latest: null,
    history: [],
    log_stream_name: "",
    message: "Runtime metrics are not available for this backend.",
    updated_at: job.updated_at,
  };
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
    remove_assets?: string[];
  },
): Promise<TrainingJobModelOutputSummary> => {
  const formData = new FormData();
  formData.append("output_revision", String(payload.output_revision));
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
