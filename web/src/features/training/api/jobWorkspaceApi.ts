import { apiClient } from "@/shared/api/client";
import { isAxiosError } from "axios";
import { controlPlaneURL } from "@/shared/api/config";
import type { TrainingJob } from "@/features/training/types";
import type {
  InputFileKind,
  InputFileSelection,
} from "@/features/training/components/InputFileDialog";

export interface WorkspaceEntry {
  id: string;
  path: string;
  kind: InputFileKind | "folder";
  size_bytes: number;
  download_url?: string;
}
export interface TrainingWorkspace extends Pick<
  TrainingJob,
  | "id"
  | "entry_point"
  | "model_flavor"
  | "vcpu"
  | "memory_mb"
  | "max_runtime_seconds"
  | "accelerator_type"
  | "accelerator_count"
  | "accelerator_model"
  | "local_gpu_id"
  | "created_at"
  | "updated_at"
  | "deletion_requested_at"
  | "deletion_error"
> {
  status: "ready" | "preparing" | "running" | "deleting" | "delete_failed";
  job_count: number;
  active_job_id: string | null;
  outputs_purged_at?: string | null;
  id: string;
  revision: number;
  entry_point: string;
  entries: WorkspaceEntry[];
  environment: Record<string, string>;
  secrets: { name: string; updated_at: string }[];
  secrets_available: boolean;
}
const url = (id?: string) =>
  controlPlaneURL(`/training-workspaces/${id ? `${id}/` : ""}`);
export const createTrainingWorkspace = async () =>
  (await apiClient.post<TrainingWorkspace>(url(), {})).data;
export const getTrainingWorkspace = async (id: string) =>
  (await apiClient.get<TrainingWorkspace>(url(id))).data;
export const updateTrainingWorkspace = async (
  id: string,
  revision: number,
  changes: Partial<
    Pick<
      TrainingWorkspace,
      | "entry_point"
      | "environment"
      | "model_flavor"
      | "vcpu"
      | "memory_mb"
      | "max_runtime_seconds"
      | "accelerator_type"
      | "accelerator_count"
      | "accelerator_model"
      | "local_gpu_id"
    >
  >,
) =>
  (await apiClient.patch<TrainingWorkspace>(url(id), { revision, ...changes }))
    .data;
export const runTrainingWorkspace = async (
  id: string,
  revision: number,
  runKey: string,
) =>
  (
    await apiClient.post<TrainingJob>(`${url(id)}runs/`, {
      revision,
      run_key: runKey,
    })
  ).data;

export const isRunResponseError = (error: unknown): boolean =>
  isAxiosError(error) && Boolean(error.response);

export async function saveWorkspaceEntry(
  id: string,
  revision: number,
  selection: InputFileSelection | { path: string; kind: "folder"; file: null },
  entryId?: string,
  content?: string,
) {
  const form = new FormData();
  form.append("revision", String(revision));
  form.append("path", selection.path);
  form.append("kind", selection.kind);
  if (selection.file) form.append("file", selection.file);
  if (content !== undefined) form.append("content", content);
  return (
    await apiClient.request<{ entry: WorkspaceEntry; revision: number }>({
      url: `${url(id)}entries/${entryId ? `${entryId}/` : ""}`,
      method: entryId ? "PATCH" : "POST",
      data: form,
    })
  ).data;
}
export const deleteWorkspaceEntry = async (
  id: string,
  entry: string,
  revision: number,
) =>
  (
    await apiClient.delete<{ revision: number }>(
      `${url(id)}entries/${entry}/`,
      { data: { revision } },
    )
  ).data;
export const putWorkspaceSecret = async (
  id: string,
  revision: number,
  name: string,
  value: string,
) =>
  (
    await apiClient.put<{ revision: number }>(
      `${url(id)}secrets/${encodeURIComponent(name)}/`,
      { revision, value },
    )
  ).data;
export const deleteWorkspaceSecret = async (
  id: string,
  revision: number,
  name: string,
) =>
  (
    await apiClient.delete<{ revision: number }>(
      `${url(id)}secrets/${encodeURIComponent(name)}/`,
      { data: { revision } },
    )
  ).data;
export const getRunInput = async (id: string) =>
  (
    await apiClient.get<{ entries: WorkspaceEntry[]; entry_point: string }>(
      controlPlaneURL(`/training-jobs/${id}/input/`),
    )
  ).data;
export const getRunFile = async (id: string, path: string) =>
  (
    await apiClient.get<{ content: string }>(
      controlPlaneURL(`/training-jobs/${id}/input/`),
      { params: { path } },
    )
  ).data.content;
export async function downloadWorkspaceSelection(
  id: string,
  area: "input" | "outputs",
  path?: string | null,
  revision?: number,
) {
  const response = await apiClient
    .get<Blob>(
      revision !== undefined
        ? `${url(id)}input/download/`
        : controlPlaneURL(`/training-jobs/${id}/${area}/download/`),
      {
        params: {
          ...(path ? { path } : {}),
          ...(revision !== undefined ? { revision } : {}),
        },
        responseType: "blob",
        timeout: 120000,
      },
    )
    .catch(async (error: unknown) => {
      if (isAxiosError(error) && error.response?.data instanceof Blob) {
        try {
          error.response.data = JSON.parse(await error.response.data.text());
        } catch {
          /* Keep the original transport error. */
        }
      }
      throw error;
    });
  const filename =
    path?.split("/").pop() ?? (area === "input" ? "input" : "output");
  const disposition = String(response.headers["content-disposition"] ?? "");
  const encoded = /filename\*=utf-8''([^;]+)/i.exec(disposition)?.[1];
  const plain = /filename="([^"]+)"/i.exec(disposition)?.[1];
  const fallback = `${filename}${response.headers["content-type"] === "application/zip" && !filename.endsWith(".zip") ? ".zip" : ""}`;
  return {
    blob: response.data,
    filename: encoded ? decodeURIComponent(encoded) : (plain ?? fallback),
  };
}
export const downloadRunOutput = async (id: string, outputId: string) =>
  (
    await apiClient.get<{ download_url: string }>(
      controlPlaneURL(`/training-jobs/${id}/outputs/${outputId}/download/`),
    )
  ).data.download_url;
export async function assignTrainingProject(
  id: string,
  outputRevision: number,
  project:
    | { project_id: string }
    | {
        new_project: {
          id: string;
          name: string;
          description: string;
          access_mode: "private" | "public";
        };
      },
  selection: {
    modelId: string;
    artifacts: Record<string, string>;
    files: Record<string, File | null>;
  },
) {
  const data = new FormData();
  data.append("output_revision", String(outputRevision));
  data.append("model_id", selection.modelId);
  data.append("artifacts", JSON.stringify(selection.artifacts));
  if ("project_id" in project) data.append("project_id", project.project_id);
  else data.append("new_project", JSON.stringify(project.new_project));
  for (const [slot, file] of Object.entries(selection.files))
    if (file) data.append(slot + "_file", file);
  return (
    await apiClient.post<TrainingJob>(
      controlPlaneURL(`/training-jobs/${id}/project/`),
      data,
    )
  ).data;
}

export async function readEntry(entry: WorkspaceEntry) {
  if (!entry.download_url) return "";
  const response = await fetch(entry.download_url, {
    credentials: "omit",
    signal: AbortSignal.timeout(30000),
  });
  if (!response.ok)
    throw new Error(`File download failed (${response.status}).`);
  return response.text();
}

export const listTrainingWorkspaces = async (project?: string) =>
  (
    await apiClient.get<{ workspaces: TrainingWorkspace[] }>(url(), {
      params: { project },
    })
  ).data;
export const deleteTrainingWorkspace = async (id: string) =>
  apiClient.delete(url(id));
export const listWorkspaceJobs = async (id: string, page = 1) =>
  (
    await apiClient.get<{
      training_jobs: TrainingJob[];
      count: number;
      page: number;
      page_size: number;
    }>(`${url(id)}jobs/`, { params: { page } })
  ).data;
export const getWorkspaceJob = async (id: string, job: string) =>
  (await apiClient.get<TrainingJob>(`${url(id)}jobs/${job}/`)).data;

export async function listAllWorkspaceJobs(id: string) {
  const jobs: TrainingJob[] = [];
  let page = 1;
  let response;
  do {
    response = await listWorkspaceJobs(id, page++);
    jobs.push(...response.training_jobs);
  } while (jobs.length < response.count && response.training_jobs.length > 0);
  return jobs;
}
