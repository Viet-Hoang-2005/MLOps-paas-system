import { apiClient } from './client';
import { controlPlaneURL } from './config';
import type { RuntimeLogBatch, RuntimeLogSource } from '@/shared/types';

interface RuntimeLogDTO {
  logs: string[];
  next_offset: number;
  status: string;
  error_message: string;
}

const runtimeLogPath = (source: RuntimeLogSource) => {
  if (source.kind === 'build') return `/builds/${source.id}/logs/`;
  if (source.kind === 'deployment') return `/deployments/${source.id}/logs/`;
  if (source.kind === 'training') return `/training-jobs/${source.id}/logs/`;
  return `/drift-monitors/runs/${source.id}/logs/`;
};

export const getRuntimeLogs = async (
  source: RuntimeLogSource,
  offset: number,
): Promise<RuntimeLogBatch> => {
  const { data } = await apiClient.get<RuntimeLogDTO>(controlPlaneURL(runtimeLogPath(source)), {
    params: { offset },
  });
  return {
    logs: data.logs ?? [],
    nextOffset: data.next_offset ?? offset,
    status: data.status,
    error: data.error_message ?? '',
  };
};
