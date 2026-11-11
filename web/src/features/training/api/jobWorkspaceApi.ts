import { apiClient } from "@/shared/api/client";
import { controlPlaneURL } from "@/shared/api/config";
import type { TrainingJob } from "@/features/training/types";
import type { TrainingFileKind, TrainingFileSelection } from "@/features/training/components/TrainingFileDialog";

export interface WorkspaceEntry {
  id: string;
  path: string;
  kind: TrainingFileKind | "folder";
  size_bytes: number;
  download_url?: string;
}
export interface JobWorkspace extends TrainingJob {
  id: string; revision: number; entry_point: string;
  entries: WorkspaceEntry[]; environment: Record<string, string>;
  secrets: { name: string; updated_at: string }[]; secrets_available: boolean;
}
const url = (id?: string) => controlPlaneURL(`/training-jobs/${id ? `${id}/` : ""}`);
export const createJobDraft = async () => (await apiClient.post<JobWorkspace>(url(), {})).data;
export const getJobWorkspace = async (id: string) => (await apiClient.get<JobWorkspace>(url(id))).data;
export const updateJobWorkspace = async (id: string, revision: number, changes: Partial<Pick<JobWorkspace, "entry_point" | "environment" | "model_flavor" | "vcpu" | "memory_mb" | "max_runtime_seconds" | "accelerator_type" | "accelerator_count" | "accelerator_model" | "local_gpu_id">>) =>
  (await apiClient.patch<JobWorkspace>(url(id), { revision, ...changes })).data;
export const runJob = async (id: string, revision: number, runKey: string) =>
  (await apiClient.post<TrainingJob>(`${url(id)}submit/`, { revision, run_key: runKey })).data;

export async function saveJobEntry(id: string, revision: number, selection: TrainingFileSelection | { path: string; kind: "folder"; file: null }, entryId?: string, content?: string) {
  const form = new FormData();
  form.append("revision", String(revision)); form.append("path", selection.path); form.append("kind", selection.kind);
  if (selection.file) form.append("file", selection.file);
  if (content !== undefined) form.append("content", content);
  return (await apiClient.request<{ entry: WorkspaceEntry; revision: number }>({
    url: `${url(id)}entries/${entryId ? `${entryId}/` : ""}`, method: entryId ? "PATCH" : "POST", data: form,
  })).data;
}
export const deleteJobEntry = async (id: string, entry: string, revision: number) =>
  (await apiClient.delete<{ revision: number }>(`${url(id)}entries/${entry}/`, { data: { revision } })).data;
export const putJobSecret = async (id: string, revision: number, name: string, value: string) =>
  (await apiClient.put<{ revision: number }>(`${url(id)}secrets/${encodeURIComponent(name)}/`, { revision, value })).data;
export const deleteJobSecret = async (id: string, revision: number, name: string) =>
  (await apiClient.delete<{ revision: number }>(`${url(id)}secrets/${encodeURIComponent(name)}/`, { data: { revision } })).data;
export const getRunInput = async (id: string) =>
  (await apiClient.get<{ entries: WorkspaceEntry[]; entry_point: string }>(controlPlaneURL(`/training-jobs/${id}/input/`))).data;
export const getRunFile = async (id: string, path: string) =>
  (await apiClient.get<{ content: string }>(controlPlaneURL(`/training-jobs/${id}/input/`), { params: { path } })).data.content;
export const downloadRunInput = async (id: string) =>
  (await apiClient.get<{ download_url: string }>(controlPlaneURL(`/training-jobs/${id}/input/`), { params: { download: "1" } })).data.download_url;
export const downloadRunOutput = async (id: string, outputId: string) =>
  (await apiClient.get<{ download_url: string }>(controlPlaneURL(`/training-jobs/${id}/outputs/${outputId}/download/`))).data.download_url;
export const assignTrainingProject = async (id: string, outputRevision: number, project: { project_id: string } | { new_project: { id: string; name: string; description: string; access_mode: "private" | "public" } }) =>
  (await apiClient.post<TrainingJob>(controlPlaneURL(`/training-jobs/${id}/project/`), { output_revision: outputRevision, ...project })).data;

export async function readEntry(entry: WorkspaceEntry) {
  if (!entry.download_url) return "";
  const response = await fetch(entry.download_url, { credentials: "omit", signal: AbortSignal.timeout(30000) });
  if (!response.ok) throw new Error(`File download failed (${response.status}).`);
  return response.text();
}
