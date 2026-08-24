import { apiClient } from '@/shared/api/client';
import { controlPlaneURL } from '@/shared/api/config';
import type {
  APIKeyListResponse,
  APIKeyRecord,
  CreateAPIKeyRequest,
  CreatedAPIKeyResponse,
} from '@/features/settings/types';
import type { MessageResponse } from '@/shared/types';

interface APIKeyDTO {
  id: string;
  name: string;
  description: string;
  key?: string;
  key_prefix: string;
  allowed_projects: string[];
  created_at: string;
}

const toRequest = (payload: CreateAPIKeyRequest) => ({
  name: payload.name,
  description: payload.description,
  allowed_projects: payload.allowed_models,
});

const toRecord = (key: APIKeyDTO): APIKeyRecord => ({
  ...key,
  scope: 'specific',
  allowed_models: key.allowed_projects,
});

const toCreated = (data: APIKeyDTO, message: string): CreatedAPIKeyResponse => ({
  ...toRecord(data),
  message,
  api_key: data.key ?? '',
});

export const createAPIKey = async (payload: CreateAPIKeyRequest): Promise<CreatedAPIKeyResponse> =>
  toCreated((await apiClient.post<APIKeyDTO>(controlPlaneURL('/api-keys/'), toRequest(payload))).data, 'API key created.');

export const listAPIKeys = async (): Promise<APIKeyListResponse> => {
  const { data } = await apiClient.get<{ results?: APIKeyDTO[] }>(controlPlaneURL('/api-keys/'));
  return { tenant_id: '', api_keys: (data.results ?? []).map(toRecord) };
};

export const updateAPIKey = async (
  keyId: string,
  payload: CreateAPIKeyRequest,
): Promise<APIKeyRecord & MessageResponse> => ({
  ...toRecord((await apiClient.put<APIKeyDTO>(controlPlaneURL(`/api-keys/${keyId}/`), toRequest(payload))).data),
  message: 'API key updated.',
});

export const deleteAPIKey = async (keyId: string): Promise<MessageResponse> => {
  await apiClient.delete(controlPlaneURL(`/api-keys/${keyId}/`));
  return { message: 'API key revoked.' };
};

export const regenerateAPIKey = async (keyId: string): Promise<CreatedAPIKeyResponse> =>
  toCreated((await apiClient.post<APIKeyDTO>(controlPlaneURL(`/api-keys/${keyId}/regenerate/`))).data, 'API key regenerated.');
