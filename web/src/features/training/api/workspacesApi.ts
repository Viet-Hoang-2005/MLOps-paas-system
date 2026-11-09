import { apiClient } from "@/shared/api/client";
import { controlPlaneURL } from "@/shared/api/config";
import type { TrainingJob, TrainingJobFormValues } from "@/features/training/types";
import type { TrainingFileKind, TrainingFileSelection } from "@/features/training/components/TrainingFileDialog";

export interface WorkspaceEntry {
  id: string;
  path: string;
  kind: TrainingFileKind | "folder";
  size_bytes: number;
  download_url?: string;
}
export interface TrainingWorkspace {
  id: string; name: string; revision: number; entry_point: string;
  entries: WorkspaceEntry[]; environment: Record<string, string>;
  secrets: { name: string; updated_at: string }[]; secrets_available: boolean;
}
const url = (id?: string) => controlPlaneURL(`/training-workspaces/${id ? `${id}/` : ""}`);
export const createWorkspace = async () => (await apiClient.post<TrainingWorkspace>(url(), {})).data;
export const getWorkspace = async (id: string) => (await apiClient.get<TrainingWorkspace>(url(id))).data;
export const listWorkspaces = async () => (await apiClient.get<Pick<TrainingWorkspace, "id" | "name" | "revision">[]>(url())).data;
export const updateWorkspace = async (id: string, revision: number, changes: Partial<Pick<TrainingWorkspace, "name" | "entry_point" | "environment">>) =>
  (await apiClient.patch<TrainingWorkspace>(url(id), { revision, ...changes })).data;
export const listWorkspaceRuns = async (id: string) => (await apiClient.get<TrainingJob[]>(`${url(id)}runs/`)).data;
export const runWorkspace = async (id: string, revision: number, runKey: string, values: TrainingJobFormValues) =>
  (await apiClient.post<TrainingJob>(`${url(id)}runs/`, {
    revision, run_key: runKey, name: values.name, model_flavor: values.model_flavor,
    vcpu: values.vcpu, memory_mb: values.memory, max_runtime_seconds: values.max_runtime_seconds,
    accelerator_type: values.accelerator_type, accelerator_count: values.accelerator_count,
    accelerator_model: values.accelerator_model, local_gpu_id: values.local_gpu_id,
  })).data;

export async function saveWorkspaceEntry(id: string, revision: number, selection: TrainingFileSelection | { path: string; kind: "folder"; file: null }, entryId?: string, content?: string) {
  const form = new FormData();
  form.append("revision", String(revision)); form.append("path", selection.path); form.append("kind", selection.kind);
  if (selection.file) form.append("file", selection.file);
  if (content !== undefined) form.append("content", content);
  return (await apiClient.request<{ entry: WorkspaceEntry; revision: number }>({
    url: `${url(id)}entries/${entryId ? `${entryId}/` : ""}`, method: entryId ? "PATCH" : "POST", data: form,
  })).data;
}
export const deleteWorkspaceEntry = async (id: string, entry: string, revision: number) =>
  (await apiClient.delete<{ revision: number }>(`${url(id)}entries/${entry}/`, { data: { revision } })).data;
export const putWorkspaceSecret = async (id: string, revision: number, name: string, value: string) =>
  (await apiClient.put<{ revision: number }>(`${url(id)}secrets/${encodeURIComponent(name)}/`, { revision, value })).data;
export const deleteWorkspaceSecret = async (id: string, revision: number, name: string) =>
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
