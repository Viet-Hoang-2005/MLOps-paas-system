import { apiClient } from "@/shared/api/client";
import { controlPlaneURL } from "@/shared/api/config";

export type DraftAssetKind =
  | "model"
  | "reference_data"
  | "source_code"
  | "data_contract"
  | "label_mapping"
  | "metrics"
  | "params"
  | "model_insights"
  | "feature_importance"
  | "input_schema";

export interface DraftAsset {
  id: string;
  kind: DraftAssetKind;
  name: string;
  download_url: string;
  checksum: string;
  size_bytes: number;
  content_type: string;
}

export interface ModelDraft {
  id: string;
  flavor: string;
  artifact_format: "raw" | "archive";
  requirements_snapshot: string;
  revision: number;
  saved_revision: number;
  saved_snapshot_id: string | null;
  saved_at: string | null;
  status: "editing" | "saving" | "ready" | "locked";
  is_dirty: boolean;
  can_build: boolean;
  has_mandatory_assets: boolean;
  assets: DraftAsset[];
}

const draftUrl = (projectId: string) => controlPlaneURL(`/models/${projectId}/draft/`);

export const getDraft = async (projectId: string): Promise<ModelDraft> =>
  (await apiClient.get<ModelDraft>(draftUrl(projectId))).data;

export const patchDraft = async (
  projectId: string,
  expected_revision: number,
  fields: Pick<ModelDraft, "flavor" | "artifact_format" | "requirements_snapshot">,
): Promise<ModelDraft> =>
  (await apiClient.patch<ModelDraft>(draftUrl(projectId), { expected_revision, ...fields })).data;

export const uploadDraftAsset = async (
  projectId: string,
  kind: DraftAssetKind,
  file: File,
): Promise<DraftAsset> => {
  const checksumBytes = await crypto.subtle.digest("SHA-256", await file.arrayBuffer());
  const checksum = Array.from(new Uint8Array(checksumBytes), (byte) => byte.toString(16).padStart(2, "0")).join("");
  const { data: session } = await apiClient.post<{
    upload_id: string;
    upload_url: string;
    headers: Record<string, string>;
  }>(controlPlaneURL(`/models/${projectId}/draft/assets/upload-url/`), {
    kind,
    filename: file.name,
    size_bytes: file.size,
    checksum,
    content_type: file.type || "application/octet-stream",
  });
  const upload = await fetch(session.upload_url, { method: "PUT", headers: session.headers, body: file });
  if (!upload.ok) throw new Error(`Direct asset upload failed (${upload.status}).`);
  return (await apiClient.post<DraftAsset>(controlPlaneURL(`/models/${projectId}/draft/assets/complete/`), {
    upload_id: session.upload_id,
  })).data;
};

export const removeDraftAsset = async (projectId: string, kind: DraftAssetKind): Promise<void> => {
  await apiClient.delete(controlPlaneURL(`/models/${projectId}/draft/assets/${kind}/`));
};

export const saveDraft = async (projectId: string, expected_revision: number): Promise<ModelDraft> =>
  (await apiClient.post<ModelDraft>(controlPlaneURL(`/models/${projectId}/draft/save/`), { expected_revision })).data;

export const discardDraft = async (projectId: string): Promise<ModelDraft> =>
  (await apiClient.post<ModelDraft>(controlPlaneURL(`/models/${projectId}/draft/discard/`))).data;

export const loadVersionIntoDraft = async (projectId: string, version_id: string): Promise<ModelDraft> =>
  (await apiClient.post<ModelDraft>(controlPlaneURL(`/models/${projectId}/draft/load-version/`), { version_id, confirm: true })).data;

export const buildDraft = async (projectId: string) =>
  (await apiClient.post(controlPlaneURL(`/models/${projectId}/draft/build/`), {})).data;
