import { apiClient } from '@/shared/api/client';
import { controlPlaneURL } from '@/shared/api/config';
import { listModelProjects } from '@/features/catalog/api/catalogApi';
import { getProjectVersions, listBuilds } from '@/features/deploy/api/deployApi';
import type { ModelVersion } from '@/features/catalog/types';
import type {
  PromoteAliasResponse,
  RegistryFamily,
  RegistryHistory,
  RegistryMetric,
  RegistrySmokeTestRequest,
  RegistrySmokeTestResponse,
  RegistryVersion,
  RegistryVersionCompareResponse,
  RoutingAliasName,
} from '@/features/registry/types';

const asRegistryVersion = (version: ModelVersion): RegistryVersion => ({
  id: version.id,
  project_id: version.project_id,
  version: version.version,
  source_type: version.source_job_id ? 'training_job' : 'manual_upload',
  source_training_job: version.source_job_id,
  source_training_job_id: version.source_job_id,
  artifact_uri: version.artifacts[0]?.uri ?? '',
  image_name: '',
  endpoint_url: '',
  stage: version.stage,
  metrics_summary: version.metrics_summary,
  params_summary: version.params_summary,
  model_insights_summary: version.insights_summary,
  deployability_status: version.deployability,
  deployability_reason: version.deployability_reason,
  can_build: false,
  can_deploy: version.deployability === 'deployable',
  created_at: version.registered_at,
  updated_at: version.registered_at,
});

export const getRegistryFamilies = async (): Promise<RegistryFamily[]> => {
  const { models } = await listModelProjects();
  return models.map((project) => ({
    id: project.id,
    name: project.name,
    display_name: project.name,
    description: project.description,
    current_production_version: null,
    is_active: project.is_active,
    created_at: project.created_at,
    updated_at: project.updated_at,
  }));
};

export const getRegistryVersions = async (familyId: string): Promise<RegistryVersion[]> =>
  (await getProjectVersions(familyId)).map(asRegistryVersion);

export const getRegistryVersion = async (versionId: string): Promise<RegistryVersion> =>
  asRegistryVersion((await apiClient.get<ModelVersion>(controlPlaneURL(`/registry/versions/${versionId}/`))).data);

export const getRegistryMetrics = async (
  familyId: string,
  versionId: string,
): Promise<Record<string, RegistryMetric[]>> => {
  void familyId;
  const { data } = await apiClient.get<ModelVersion & {
    metrics?: Array<{
      id: string;
      name: string;
      value: number;
      step: number | null;
      timestamp: string | null;
      metadata: Record<string, unknown>;
    }>;
  }>(controlPlaneURL(`/registry/versions/${versionId}/`));
  return {
    metrics: (data.metrics ?? []).map((metric) => ({
      id: metric.id,
      metric_name: metric.name,
      value: metric.value,
      step: metric.step ?? 0,
      source: 'registry',
      created_at: metric.timestamp ?? data.registered_at,
      extra: metric.metadata,
    })),
  };
};

export const getRegistryHistory = async (familyId: string): Promise<RegistryHistory[]> => {
  const versions = await getProjectVersions(familyId);
  return versions.flatMap((version) => {
    const events = (version as ModelVersion & {
      events?: Array<{
        id: string;
        event_type: string;
        from_state: string;
        to_state: string;
        created_at: string;
      }>;
    }).events ?? [];
    return events.map((event) => ({
      id: event.id,
      action: event.event_type,
      status: 'success' as const,
      version: version.version,
      from_stage: event.from_state,
      to_stage: event.to_state,
      message: event.event_type,
      actor: '',
      created_at: event.created_at,
    }));
  });
};

export const compareRegistryVersions = async (
  familyId: string,
  leftVersionId: string,
  rightVersionId: string,
): Promise<RegistryVersionCompareResponse> => {
  const [left, right, families] = await Promise.all([
    getRegistryVersion(leftVersionId),
    getRegistryVersion(rightVersionId),
    getRegistryFamilies(),
  ]);
  const family = families.find((item) => item.id === familyId);
  if (!family) throw new Error('Model project not found.');
  return {
    family,
    left,
    right,
    metrics_diff: [],
    params_diff: [],
    artifact_diff: { added: [], removed: [], changed: [], unchanged_count: 0 },
    deployability_diff: {
      left: { status: left.deployability_status ?? 'unknown', reason: left.deployability_reason ?? '' },
      right: { status: right.deployability_status ?? 'unknown', reason: right.deployability_reason ?? '' },
    },
    deployment_diff: {
      left_stage: left.stage,
      right_stage: right.stage,
      left_endpoint_url: left.endpoint_url,
      right_endpoint_url: right.endpoint_url,
      left_deployed: false,
      right_deployed: false,
      left_image_name: left.image_name,
      right_image_name: right.image_name,
    },
    recommendation: {
      winner: 'unknown',
      confidence: 'low',
      reason: 'Compare metrics to choose a version.',
      warnings: [],
    },
  };
};

export const promoteRegistryVersion = async (
  familyId: string,
  versionId: string,
  alias: RoutingAliasName = 'production',
): Promise<PromoteAliasResponse> => {
  await apiClient.post(controlPlaneURL(`/registry/models/${familyId}/aliases/`), {
    name: alias,
    version: versionId,
  });
  return { success: true, message: `Alias ${alias} now points to the selected version.` };
};

export const predictViaRoutingAlias = async (
  familyId: string,
  alias: RoutingAliasName,
  payload: unknown,
): Promise<unknown> =>
  (await apiClient.post(controlPlaneURL(`/registry/models/${familyId}/aliases/${alias}/predict/`), payload)).data;

export const rollbackRegistryFamily = async (
  familyId: string,
  versionId: string,
): Promise<RegistryVersion> => {
  await promoteRegistryVersion(familyId, versionId, 'production');
  return getRegistryVersion(versionId);
};

export const deployRegistryVersion = async (versionId: string): Promise<RegistryVersion> => {
  const build = (await listBuilds()).find((item) => item.version_id === versionId && item.status === 'ready');
  if (!build) throw new Error('No ready build exists for this version.');
  await apiClient.post(controlPlaneURL('/deployments/'), { build: build.id });
  return getRegistryVersion(versionId);
};

export const checkRegistryVersionHealth = getRegistryVersion;

export const smokeTestRegistryVersion = async (
  versionId: string,
  payload: RegistrySmokeTestRequest,
): Promise<RegistrySmokeTestResponse> =>
  (await apiClient.post<RegistrySmokeTestResponse>(
    controlPlaneURL(`/registry/versions/${versionId}/smoke-test/`),
    payload,
  )).data;
