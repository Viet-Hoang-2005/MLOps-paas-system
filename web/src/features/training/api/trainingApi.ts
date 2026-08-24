import { apiClient } from '@/shared/api/client';
import { controlPlaneURL } from '@/shared/api/config';
import { pageResults } from '@/shared/api/pagination';
import type {
  TrainingBuild,
  TrainingJob,
  TrainingJobDownloadURLResponse,
  TrainingJobDeletionRequest,
  TrainingJobEventsResponse,
  TrainingJobFormValues,
  TrainingJobListResponse,
  TrainingJobLogsResponse,
  TrainingJobMetricsResponse,
  TrainingJobStatus,
  TrainingRuntimeCapabilities,
  TrainingUsageResponse,
} from '@/features/training/types';

const trainingJobFormData = (payload: TrainingJobFormValues) => {
  const formData = new FormData();
  formData.append('name', payload.name);
  formData.append('model_flavor', payload.model_flavor);
  formData.append('project', payload.project_id || '');
  formData.append('entry_point', payload.entry_point || 'train.py');
  formData.append('requirements_text', payload.requirements_text);
  formData.append('vcpu', String(payload.vcpu));
  formData.append('memory_mb', String(payload.memory));
  formData.append('max_runtime_seconds', String(payload.max_runtime_seconds));
  formData.append('accelerator_type', payload.accelerator_type);
  formData.append('accelerator_count', String(payload.accelerator_count));
  if (payload.source_zip) formData.append('source_zip', payload.source_zip);
  if (payload.training_data) formData.append('training_data', payload.training_data);
  return formData;
};

export const createTrainingJob = async (payload: TrainingJobFormValues): Promise<TrainingJob> => {
  const { data: job } = await apiClient.post<TrainingJob>(
    controlPlaneURL('/training-jobs/'),
    trainingJobFormData(payload),
    { headers: { 'Content-Type': 'multipart/form-data' } },
  );
  return (await apiClient.post<TrainingJob>(controlPlaneURL(`/training-jobs/${job.id}/submit/`))).data;
};

export const listTrainingJobs = async (): Promise<TrainingJobListResponse> => {
  const { data } = await apiClient.get<{ results: TrainingJob[] } | TrainingJob[]>(controlPlaneURL('/training-jobs/'));
  return { training_jobs: pageResults(data) };
};

export const getTrainingUsage = async (): Promise<TrainingUsageResponse> => {
  const { training_jobs: jobs } = await listTrainingJobs();
  const monthlyRuntime = jobs.reduce((total, job) => total + job.runtime_seconds, 0);
  const trainingBackend = ['argo', 'kubeflow'].includes(jobs[0]?.backend ?? '') ? 'kubeflow' : 'local';
  return {
    training_backend: trainingBackend,
    monthly_quota_seconds: 0,
    monthly_runtime_seconds: monthlyRuntime,
    remaining_seconds: 0,
    active_jobs_count: jobs.filter((job) =>
      ['pending', 'queued', 'uploading', 'running', 'cancelling'].includes(job.status),
    ).length,
    running_jobs_count: jobs.filter((job) => job.status === 'running').length,
    completed_jobs_count: jobs.filter((job) => job.status === 'completed').length,
    failed_jobs_count: jobs.filter((job) => job.status === 'failed').length,
    current_month_start: '',
    current_month_end: '',
  };
};

export const getTrainingJob = async (jobId: string): Promise<TrainingJob> =>
  (await apiClient.get<TrainingJob>(controlPlaneURL(`/training-jobs/${jobId}/`))).data;

export const refreshTrainingJobStatus = getTrainingJob;

export const getTrainingJobDownloadUrl = async (jobId: string): Promise<TrainingJobDownloadURLResponse> =>
  (await apiClient.get<TrainingJobDownloadURLResponse>(controlPlaneURL(`/training-jobs/${jobId}/download/`))).data;

export const buildAndRegisterTrainingJob = async (jobId: string): Promise<TrainingBuild> =>
  (await apiClient.post<TrainingBuild>(controlPlaneURL(`/training-jobs/${jobId}/build/`))).data;

export const deleteTrainingOutputs = async (jobId: string): Promise<TrainingJob> =>
  (await apiClient.delete<TrainingJob>(controlPlaneURL(`/training-jobs/${jobId}/outputs/`))).data;

export const getTrainingRuntimeCapabilities = async (): Promise<TrainingRuntimeCapabilities> =>
  (await apiClient.get<TrainingRuntimeCapabilities>(controlPlaneURL('/training-jobs/runtime-capabilities/'))).data;

export const getTrainingJobLogs = async (jobId: string, offset = 0): Promise<TrainingJobLogsResponse> => {
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
    text: data.logs.join('\n'),
    next_offset: data.next_offset,
    error_message: data.error_message,
  };
};

export const getTrainingJobMetrics = async (jobId: string): Promise<TrainingJobMetricsResponse> => {
  const job = await getTrainingJob(jobId);
  return {
    job_id: job.id,
    training_job_id: job.id,
    status: job.status,
    metrics_available: false,
    latest: null,
    history: [],
    log_stream_name: '',
    message: 'Runtime metrics are not available for this backend.',
    updated_at: job.updated_at,
  };
};

export const getTrainingJobEvents = async (jobId: string): Promise<TrainingJobEventsResponse> => ({
  events: (await apiClient.get<TrainingJobEventsResponse['events']>(
    controlPlaneURL(`/training-jobs/${jobId}/events/`),
  )).data,
});

export const cancelTrainingJob = async (jobId: string): Promise<TrainingJob> => {
  const { data } = await apiClient.post<TrainingJob | { training_job: TrainingJob }>(
    controlPlaneURL(`/training-jobs/${jobId}/cancel/`),
  );
  return 'training_job' in data ? data.training_job : data;
};

export const retryTrainingJob = async (jobId: string): Promise<TrainingJob> => {
  const previous = await getTrainingJob(jobId);
  const { data: job } = await apiClient.post<TrainingJob>(controlPlaneURL('/training-jobs/'), {
    project: previous.project_id,
    name: previous.name,
    model_flavor: previous.model_flavor,
    entry_point: previous.entry_point,
    requirements_text: previous.requirements_text,
    code_snapshot_uri: previous.code_snapshot_uri,
    data_snapshot_uri: previous.data_snapshot_uri,
    backend: previous.backend,
    vcpu: previous.vcpu,
    memory_mb: previous.memory_mb,
    max_runtime_seconds: previous.max_runtime_seconds,
    accelerator_type: previous.accelerator_type,
    accelerator_count: previous.accelerator_count,
  });
  return (await apiClient.post<TrainingJob>(controlPlaneURL(`/training-jobs/${job.id}/submit/`))).data;
};

export const deleteTrainingJob = async (jobId: string): Promise<TrainingJobDeletionRequest> =>
  (await apiClient.delete<TrainingJobDeletionRequest>(controlPlaneURL(`/training-jobs/${jobId}/`))).data;
