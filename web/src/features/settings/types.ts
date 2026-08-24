export interface UserProfile {
  email: string;
  full_name: string | null;
  description: string | null;
  pronouns: string | null;
  company: string | null;
  avatar: string | null;
  field_of_work: string | null;
  country: string | null;
  tenant_id: string;
  auth_provider: string;
  date_joined: string;
}

export interface AvatarRecord {
  id: string;
  url: string;
  is_current: boolean;
  created_at: string;
}

export interface AvatarHistoryResponse {
  avatars: AvatarRecord[];
}

export interface UpdateProfileRequest {
  full_name: string;
  description: string;
  pronouns: string;
  company: string;
  field_of_work: string;
  country: string;
}

export interface UpdateProfileAvatarRequest {
  avatar?: File | null;
  remove_avatar?: boolean;
}

export interface PasswordChangeVerifyResponse {
  message: string;
  password_change_token: string;
}

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

export interface ProfileFormValues {
  fullName: string;
  description: string;
  pronouns: string;
  company: string;
  fieldOfWork: string;
  country: string;
}

export type PasswordModalStep = 'closed' | 'otp' | 'password';
export type KeyModalMode = 'create' | 'edit';

export interface APIKeyFormValues {
  name: string;
  description: string;
}

export type APIKeyActionTarget = APIKeyRecord | null;
