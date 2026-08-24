import { apiClient } from '@/shared/api/client';
import type { MessageResponse } from '@/shared/types';
import type {
  AvatarHistoryResponse,
  PasswordChangeVerifyResponse,
  UpdateProfileAvatarRequest,
  UpdateProfileRequest,
  UserProfile,
} from '@/features/settings/types';

export const getProfile = async (): Promise<UserProfile> =>
  (await apiClient.get<UserProfile>('/auth/profile/')).data;

export const updateProfile = async (payload: UpdateProfileRequest): Promise<MessageResponse> =>
  (await apiClient.put<MessageResponse>('/auth/profile/', payload)).data;

export const updateProfileAvatar = async (payload: UpdateProfileAvatarRequest): Promise<MessageResponse> => {
  const formData = new FormData();
  if (payload.avatar) formData.append('avatar', payload.avatar);
  if (payload.remove_avatar) formData.append('remove_avatar', 'true');
  return (await apiClient.put<MessageResponse>('/auth/profile/', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })).data;
};

export const listProfileAvatars = async (): Promise<AvatarHistoryResponse> =>
  (await apiClient.get<AvatarHistoryResponse>('/auth/profile/avatars/')).data;

export const selectProfileAvatar = async (avatarId: string): Promise<MessageResponse> =>
  (await apiClient.post<MessageResponse>(`/auth/profile/avatars/${avatarId}/select/`)).data;

export const deleteAccount = async (): Promise<MessageResponse> =>
  (await apiClient.delete<MessageResponse>('/auth/profile/delete/')).data;

export const requestPasswordChangeOTP = async (): Promise<MessageResponse> =>
  (await apiClient.post<MessageResponse>('/auth/profile/password-otp/')).data;

export const verifyPasswordChangeOTP = async (otpCode: string): Promise<PasswordChangeVerifyResponse> =>
  (await apiClient.post<PasswordChangeVerifyResponse>('/auth/profile/password-otp/verify/', { otp_code: otpCode })).data;

export const completePasswordChange = async (
  passwordChangeToken: string,
  newPassword: string,
): Promise<MessageResponse> =>
  (await apiClient.post<MessageResponse>('/auth/profile/change-password/', {
    password_change_token: passwordChangeToken,
    new_password: newPassword,
  })).data;
