import { apiClient } from "@/shared/api/client";
import { controlPlaneURL } from "@/shared/api/config";
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

export const getPreview = async (id: string) =>
  (await apiClient.get<ModelPreview>(controlPlaneURL(`/models/${id}/preview/`)))
    .data;

function previewData(form: ModelBuildFormValues) {
  const data = new FormData();
  data.append("flavor", form.flavor);
  data.append("artifact_format", form.artifact_format);
  data.append("requirements_text", form.requirements_text);
  const files: Array<[string, File | null | undefined]> = [
    ["source_artifact_file", form.source_artifact],
    ["source_code_file", form.source_code_file],
    ["reference_data_file", form.reference_data_file],
    ["label_mapping_file", form.label_mapping_file],
    ["metrics_file", form.metrics_file],
    ["params_file", form.params_file],
    ["model_insights_file", form.model_insights_file],
    ["feature_importance_file", form.feature_importance_file],
    ["input_schema_file", form.input_schema_file],
  ];
  files.forEach(([key, file]) => {
    if (file) data.append(key, file);
  });
  return data;
}

export async function createPreviewProject(
  form: ModelBuildFormValues,
): Promise<ModelProject> {
  const data = previewData(form);
  data.append("name", form.name);
  data.append("description", form.description);
  data.append("access_mode", form.access_mode);
  return (await apiClient.post<ModelProject>(controlPlaneURL("/models/"), data))
    .data;
}

export async function updatePreview(
  id: string,
  revision: number,
  form: ModelBuildFormValues,
  removeAssets: string[] = [],
): Promise<ModelPreview> {
  const data = previewData(form);
  data.append("revision", String(revision));
  removeAssets.forEach((kind) => data.append("remove_assets", kind));
  return (
    await apiClient.patch<ModelPreview>(
      controlPlaneURL(`/models/${id}/preview/`),
      data,
    )
  ).data;
}
