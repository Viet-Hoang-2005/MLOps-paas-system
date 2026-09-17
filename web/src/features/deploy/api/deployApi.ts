import { apiClient } from '@/shared/api/client';
import { controlPlaneURL } from '@/shared/api/config';
import { pageResults } from '@/shared/api/pagination';
import { getModelProject } from '@/features/catalog/api/catalogApi';
import type {
  Build,
  BuildInputForm,
  Deployment,
  ModelProject,
  ProjectMetadataForm,
  ModelVersion,
} from '@/features/catalog/types';

const metadataFormData = (payload: ProjectMetadataForm): FormData => {
  const data = new FormData();
  data.append('name', payload.name);
  data.append('description', payload.description);
  data.append('access_mode', payload.access_mode);
  const files: Array<[string, File | null | undefined]> = [
    ['source_code_file', payload.source_code_file],
    ['reference_data_file', payload.reference_data_file],
  ];
  files.forEach(([name, file]) => {
    if (file) data.append(name, file);
  });
  return data;
};

const buildFormData = (payload: BuildInputForm): FormData => {
  const data = new FormData();
  data.append('flavor', payload.flavor);
  data.append('artifact_format', payload.artifact_format);
  data.append('requirements_text', payload.requirements_text);
  const files: Array<[string, File | null | undefined]> = [
    ['source_artifact', payload.source_artifact],
    ['label_mapping_file', payload.label_mapping_file],
    ['metrics_file', payload.metrics_file],
    ['params_file', payload.params_file],
    ['model_insights_file', payload.model_insights_file],
    ['feature_importance_file', payload.feature_importance_file],
    ['input_schema_file', payload.input_schema_file],
  ];
  files.forEach(([name, file]) => {
    if (file) data.append(name, file);
  });
  return data;
};

export const createProjectMetadata = async (payload: ProjectMetadataForm): Promise<ModelProject> =>
  (await apiClient.post<ModelProject>(
    controlPlaneURL('/models/'),
    metadataFormData(payload),
    { headers: { 'Content-Type': 'multipart/form-data' } },
  )).data;

export const updateProjectMetadata = async (
  modelId: string,
  payload: ProjectMetadataForm,
): Promise<ModelProject> =>
  (await apiClient.put<ModelProject>(
    controlPlaneURL(`/models/${modelId}/`),
    metadataFormData(payload),
    { headers: { 'Content-Type': 'multipart/form-data' } },
  )).data;

export interface PresignedUploadResponse {
  upload_url: string;
  s3_uri: string;
  key: string;
  filename: string;
  draft_build_id: string;
  expires_in: number;
}

export const getBuildPresignedUrl = async (
  modelId: string,
  payload: {
    flavor: string;
    artifact_format: string;
    filename: string;
    content_type?: string;
  },
): Promise<PresignedUploadResponse> =>
  (
    await apiClient.post<PresignedUploadResponse>(
      controlPlaneURL(`/models/${modelId}/builds/upload-url/`),
      payload,
    )
  ).data;

export const uploadFileToPresignedUrl = async (
  uploadUrl: string,
  file: File,
  onProgress?: (percent: number) => void,
): Promise<void> => {
  return new Promise<void>((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open('PUT', uploadUrl, true);
    xhr.setRequestHeader('Content-Type', file.type || 'application/octet-stream');

    if (xhr.upload && onProgress) {
      xhr.upload.onprogress = (event) => {
        if (event.lengthComputable) {
          const percent = Math.round((event.loaded / event.total) * 100);
          onProgress(percent);
        }
      };
    }

    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve();
      } else {
        reject(new Error(`Direct S3 upload failed with status ${xhr.status}: ${xhr.statusText}`));
      }
    };

    xhr.onerror = () => {
      reject(new Error('Network error occurred during direct S3 artifact upload.'));
    };

    xhr.send(file);
  });
};

export const startProjectBuild = async (
  modelId: string,
  payload: BuildInputForm,
  onProgress?: (percent: number) => void,
): Promise<Build> => {
  // Direct-to-S3 Upload: if source_artifact is a File, upload directly to S3 via Presigned URL
  if (payload.source_artifact instanceof File) {
    const file = payload.source_artifact;
    try {
      const presigned = await getBuildPresignedUrl(modelId, {
        flavor: payload.flavor,
        artifact_format: payload.artifact_format,
        filename: file.name,
        content_type: file.type || 'application/octet-stream',
      });

      // Stream file directly to S3 bucket without routing through Control Plane
      await uploadFileToPresignedUrl(presigned.upload_url, file, onProgress);

      // Register build with Control Plane using the direct S3 URI
      const data = new FormData();
      data.append('flavor', payload.flavor);
      data.append('artifact_format', payload.artifact_format);
      data.append('requirements_text', payload.requirements_text);
      data.append('source_artifact_uri', presigned.s3_uri);
      data.append('source_artifact_name', file.name);
      data.append('source_artifact_size', String(file.size));

      const auxFiles: Array<[string, File | null | undefined]> = [
        ['label_mapping_file', payload.label_mapping_file],
        ['metrics_file', payload.metrics_file],
        ['params_file', payload.params_file],
        ['model_insights_file', payload.model_insights_file],
        ['feature_importance_file', payload.feature_importance_file],
        ['input_schema_file', payload.input_schema_file],
      ];
      auxFiles.forEach(([name, auxFile]) => {
        if (auxFile) data.append(name, auxFile);
      });

      return (
        await apiClient.post<Build>(
          controlPlaneURL(`/models/${modelId}/builds/`),
          data,
          { headers: { 'Content-Type': 'multipart/form-data' } },
        )
      ).data;
    } catch (directUploadErr) {
      console.warn('Direct-to-S3 upload failed, attempting fallback to multipart upload:', directUploadErr);
    }
  }

  // Fallback to standard multipart upload through Control Plane
  return (
    await apiClient.post<Build>(
      controlPlaneURL(`/models/${modelId}/builds/`),
      buildFormData(payload),
      { headers: { 'Content-Type': 'multipart/form-data' } },
    )
  ).data;
};

export const getBuild = async (buildId: string): Promise<Build> =>
  (await apiClient.get<Build>(controlPlaneURL(`/builds/${buildId}/`))).data;

export const cancelBuildById = async (buildId: string): Promise<Build> =>
  (await apiClient.post<Build>(controlPlaneURL(`/builds/${buildId}/cancel/`))).data;

export const listProjectBuilds = async (modelId: string): Promise<Build[]> =>
  (await apiClient.get<Build[]>(controlPlaneURL(`/models/${modelId}/builds/`))).data;

export const deployBuild = async (buildId: string): Promise<Deployment> =>
  (await apiClient.post<Deployment>(controlPlaneURL('/deployments/'), { build: buildId })).data;

export const getProjectVersions = async (projectId: string): Promise<ModelVersion[]> => {
  const { data } = await apiClient.get<{ results: ModelVersion[] } | ModelVersion[]>(
    controlPlaneURL(`/registry/models/${projectId}/versions/`),
  );
  return pageResults(data);
};

export const listBuilds = async (): Promise<Build[]> => {
  const { data } = await apiClient.get<{ results: Build[] } | Build[]>(controlPlaneURL('/builds/'));
  return pageResults(data);
};

export const listDeployments = async (): Promise<Deployment[]> => {
  const { data } = await apiClient.get<{ results: Deployment[] } | Deployment[]>(controlPlaneURL('/deployments/'));
  return pageResults(data);
};

export const deployModelProject = async (modelId: string): Promise<ModelProject> => {
  const [project, versions, builds] = await Promise.all([
    getModelProject(modelId),
    getProjectVersions(modelId),
    listBuilds(),
  ]);
  const versionIds = new Set(versions.map((version) => version.id));
  const build = builds.find((item) => item.version_id !== null && versionIds.has(item.version_id) && item.status === 'ready');
  if (!build) throw new Error('No ready build is available for this project.');
  const { data: deployment } = await apiClient.post<Deployment>(controlPlaneURL('/deployments/'), { build: build.id });
  return {
    ...project,
    deployment_id: deployment.id,
    status: 'deploying',
    endpoint_status: deployment.status === 'healthy' ? 'healthy' : 'deploying',
  };
};

export const redeployModelProject = deployModelProject;

export const stopModelEndpoint = async (modelId: string): Promise<ModelProject> => {
  const [project, deployments, versions] = await Promise.all([
    getModelProject(modelId),
    listDeployments(),
    getProjectVersions(modelId),
  ]);
  const versionIds = new Set(versions.map((version) => version.id));
  const deployment = deployments.find((item) => versionIds.has(item.version_id) && item.status !== 'stopped');
  if (deployment) await apiClient.post(controlPlaneURL(`/deployments/${deployment.id}/stop/`));
  return { ...project, status: 'stopped', endpoint_status: 'stopped' };
};

export const checkModelEndpointHealth = async (modelId: string): Promise<ModelProject> => {
  const [project, versions] = await Promise.all([getModelProject(modelId), getProjectVersions(modelId)]);
  const { data } = await apiClient.get<{
    results?: Array<{ version_id: string; public_url: string; health_status: string }>;
  }>(controlPlaneURL('/endpoints/'));
  const versionIds = new Set(versions.map((version) => version.id));
  const endpoint = (data.results ?? []).find((item) => versionIds.has(item.version_id));
  return {
    ...project,
    endpoint_url: endpoint?.public_url ?? '',
    endpoint_status: endpoint?.health_status === 'healthy' ? 'healthy' : 'unhealthy',
  };
};

export const triggerModelProjectBuild = async (modelId: string): Promise<ModelProject> => {
  const [project, versions] = await Promise.all([getModelProject(modelId), getProjectVersions(modelId)]);
  if (!versions[0]) throw new Error('Register a version before building.');
  const { data } = await apiClient.post<Build>(controlPlaneURL('/builds/'), { version: versions[0].id });
  return { ...project, build_id: data.id, build_status: data.status };
};

export const cancelBuild = async (modelId: string): Promise<void> => {
  const [versions, builds] = await Promise.all([getProjectVersions(modelId), listBuilds()]);
  const versionIds = new Set(versions.map((version) => version.id));
  const build = builds.find(
    (item) => item.version_id !== null && versionIds.has(item.version_id) && !['ready', 'failed', 'cancelled'].includes(item.status),
  );
  if (build) await apiClient.post(controlPlaneURL(`/builds/${build.id}/cancel/`));
};
