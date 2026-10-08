import { apiClient } from "@/shared/api/client";
import { controlPlaneURL } from "@/shared/api/config";
import { uploadFileToPresignedUrl } from "@/shared/api/s3Upload";
import type {
  ModelBuildFormValues,
  ModelProject,
  ModelFlavor,
  ModelArtifactFormat,
} from "@/features/projects/types";

export interface PreviewAsset {
  kind: string;
  name: string;
  download_url: string;
}

export interface ModelPreview {
  revision: number;
  flavor: ModelFlavor | "";
  artifact_format: ModelArtifactFormat;
  requirements_text: string;
  assets: PreviewAsset[];
}

export interface PresignedUploadItem {
  kind: string;
  filename: string;
  s3_uri: string;
  upload_url: string;
  content_type: string;
}

export interface PresignedUploadResponse {
  project_id: string;
  files: PresignedUploadItem[];
}

export interface UploadedAssetReference {
  kind: string;
  name: string;
  s3_uri: string;
}

interface PendingUploadFile {
  kind: string;
  file: File;
}

export const getPreview = async (id: string): Promise<ModelPreview> =>
  (await apiClient.get<ModelPreview>(controlPlaneURL(`/models/${id}/preview/`)))
    .data;

function extractFilesFromForm(form: ModelBuildFormValues): PendingUploadFile[] {
  const fileEntries: Array<[string, File | null | undefined]> = [
    ["source_artifact", form.source_artifact],
    ["source_code", form.source_code_file],
    ["reference_data", form.reference_data_file],
    ["label_mapping", form.label_mapping_file],
    ["metrics", form.metrics_file],
    ["params", form.params_file],
    ["model_insights", form.model_insights_file],
    ["feature_importance", form.feature_importance_file],
    ["input_schema", form.input_schema_file],
  ];
  return fileEntries
    .filter((entry): entry is [string, File] => Boolean(entry[1]))
    .map(([kind, file]) => ({ kind, file }));
}

export async function getPreviewUploadUrls(
  projectId: string,
  files: Array<{ kind: string; filename: string; size_bytes: number; content_type?: string }>,
  flavor?: string,
  artifact_format?: string,
): Promise<PresignedUploadResponse> {
  return (
    await apiClient.post<PresignedUploadResponse>(
      controlPlaneURL(`/models/${projectId}/preview/upload-urls/`),
      { files, flavor: flavor || undefined, artifact_format: artifact_format || undefined },
    )
  ).data;
}

export async function getNewProjectUploadUrls(
  name: string,
  files: Array<{ kind: string; filename: string; size_bytes: number; content_type?: string }>,
  flavor?: string,
  artifact_format?: string,
): Promise<PresignedUploadResponse> {
  return (
    await apiClient.post<PresignedUploadResponse>(
      controlPlaneURL("/models/preview/upload-urls/"),
      { name, files, flavor: flavor || undefined, artifact_format: artifact_format || undefined },
    )
  ).data;
}

async function uploadFilesDirectlyToS3(
  pendingFiles: PendingUploadFile[],
  presignedItems: PresignedUploadItem[],
  onProgress?: (kind: string, percent: number) => void,
): Promise<UploadedAssetReference[]> {
  const uploadedAssets: UploadedAssetReference[] = [];

  for (const item of presignedItems) {
    const pending = pendingFiles.find((p) => p.kind === item.kind);
    if (!pending) continue;

    await uploadFileToPresignedUrl(
      item.upload_url,
      pending.file,
      item.content_type,
      (percent) => {
        if (onProgress) {
          onProgress(item.kind, percent);
        }
      },
    );

    uploadedAssets.push({
      kind: item.kind,
      name: item.filename,
      s3_uri: item.s3_uri,
    });
  }

  return uploadedAssets;
}

export async function createPreviewProject(
  form: ModelBuildFormValues,
  onProgress?: (kind: string, percent: number) => void,
): Promise<ModelProject> {
  const pendingFiles = extractFilesFromForm(form);

  // Phase 1: Request presigned URLs and pre-allocated project_id
  const urlPayload = pendingFiles.map((p) => ({
    kind: p.kind,
    filename: p.file.name,
    size_bytes: p.file.size,
    content_type: p.file.type || "application/octet-stream",
  }));
  const presignedResponse = await getNewProjectUploadUrls(
    form.name,
    urlPayload,
    form.flavor,
    form.artifact_format,
  );

  // Phase 2: Upload files directly to S3
  const uploadedAssets = await uploadFilesDirectlyToS3(
    pendingFiles,
    presignedResponse.files,
    onProgress,
  );

  // Phase 3: Register project and preview in Django with verified asset references
  return (
    await apiClient.post<ModelProject>(controlPlaneURL("/models/"), {
      project_id: presignedResponse.project_id,
      name: form.name,
      description: form.description,
      access_mode: form.access_mode,
      flavor: form.flavor,
      artifact_format: form.artifact_format,
      requirements_text: form.requirements_text,
      assets: uploadedAssets,
    })
  ).data;
}

export async function updatePreview(
  id: string,
  revision: number,
  form: ModelBuildFormValues,
  removeAssets: string[] = [],
  onProgress?: (kind: string, percent: number) => void,
): Promise<ModelPreview> {
  const pendingFiles = extractFilesFromForm(form);
  let uploadedAssets: UploadedAssetReference[] = [];

  if (pendingFiles.length > 0) {
    // Phase 1: Request presigned URLs
    const urlPayload = pendingFiles.map((p) => ({
      kind: p.kind,
      filename: p.file.name,
      size_bytes: p.file.size,
      content_type: p.file.type || "application/octet-stream",
    }));
    const presignedResponse = await getPreviewUploadUrls(
      id,
      urlPayload,
      form.flavor,
      form.artifact_format,
    );

    // Phase 2: Upload directly to S3
    uploadedAssets = await uploadFilesDirectlyToS3(
      pendingFiles,
      presignedResponse.files,
      onProgress,
    );
  }

  // Phase 3: Patch preview metadata and asset references
  return (
    await apiClient.patch<ModelPreview>(
      controlPlaneURL(`/models/${id}/preview/`),
      {
        revision,
        flavor: form.flavor,
        artifact_format: form.artifact_format,
        requirements_text: form.requirements_text,
        assets: uploadedAssets,
        remove_assets: removeAssets,
      },
    )
  ).data;
}

export type PreviewSingleAssetKind =
  | "source_code"
  | "reference_data"
  | "label_mapping"
  | "input_schema"
  | "metrics"
  | "params"
  | "model_insights"
  | "feature_importance";

function getAssetContentType(kind: string, file: File): string {
  if (file.type) return file.type;
  switch (kind) {
    case "source_code":
      return "text/x-python";
    case "reference_data":
      return "text/csv";
    case "label_mapping":
      return "application/json";
    case "input_schema":
    case "metrics":
    case "params":
    case "model_insights":
    case "feature_importance":
      return "application/json";
    default:
      return "application/octet-stream";
  }
}

export async function uploadPreviewSingleAsset(
  projectId: string,
  kind: PreviewSingleAssetKind,
  file: File,
  onProgress?: (percent: number) => void,
): Promise<ModelPreview> {
  const currentPreview = await getPreview(projectId);

  const urlPayload = [
    {
      kind,
      filename: file.name,
      size_bytes: file.size,
      content_type: getAssetContentType(kind, file),
    },
  ];

  const presignedResponse = await getPreviewUploadUrls(
    projectId,
    urlPayload,
    currentPreview.flavor || undefined,
    currentPreview.artifact_format || undefined,
  );

  const item = presignedResponse.files[0];
  if (!item) {
    throw new Error("No presigned upload URL generated");
  }

  await uploadFileToPresignedUrl(
    item.upload_url,
    file,
    item.content_type,
    onProgress,
  );

  return (
    await apiClient.patch<ModelPreview>(
      controlPlaneURL(`/models/${projectId}/preview/`),
      {
        revision: currentPreview.revision,
        assets: [
          {
            kind: item.kind,
            name: item.filename,
            s3_uri: item.s3_uri,
          },
        ],
      },
    )
  ).data;
}

export async function removePreviewAsset(
  projectId: string,
  kind: PreviewSingleAssetKind,
): Promise<ModelPreview> {
  const currentPreview = await getPreview(projectId);
  return (
    await apiClient.patch<ModelPreview>(
      controlPlaneURL(`/models/${projectId}/preview/`),
      {
        revision: currentPreview.revision,
        remove_assets: [kind],
      },
    )
  ).data;
}

