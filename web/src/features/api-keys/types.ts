export interface CreateAPIKeyRequest {
  name: string;
  description: string;
  scope: string;
  allowed_models: string[];
}

export interface CreatedAPIKeyResponse {
  message: string;
  api_key: string;
  key_prefix: string;
  id: string;
  name: string;
  description: string;
  scope: string;
  allowed_models: string[];
  created_at?: string;
}

export interface APIKeyRecord {
  id: string;
  name: string;
  description: string;
  scope: string;
  allowed_models: string[];
  key_prefix: string;
  created_at: string;
}

export interface APIKeyListResponse {
  tenant_id: string;
  api_keys: APIKeyRecord[];
}

export type KeyModalMode = "create" | "edit";

export interface APIKeyFormValues {
  name: string;
  description: string;
}

export type APIKeyActionTarget = APIKeyRecord | null;
