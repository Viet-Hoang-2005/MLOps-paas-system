import { apiClient, refreshAccessToken } from '@/shared/api/client';
import type {
  AuthResponse,
  CompleteRegistrationRequest,
  LoginCredentials,
  OTPResponse,
  OTPVerifyRequest,
  OTPVerifyResponse,
  PasswordResetVerifyResponse,
  SignUpRequest,
} from '@/features/auth/types';

export const refreshSession = refreshAccessToken;

export const loginBaseAuth = async (credentials: LoginCredentials): Promise<AuthResponse> =>
  (await apiClient.post<AuthResponse>('/auth/token/', credentials)).data;

export const requestOTP = async (payload: SignUpRequest): Promise<OTPResponse> =>
  (await apiClient.post<OTPResponse>('/auth/register/request-otp/', payload)).data;

export const verifyOTP = async (payload: OTPVerifyRequest): Promise<OTPVerifyResponse> =>
  (await apiClient.post<OTPVerifyResponse>('/auth/register/verify-otp/', payload)).data;

export const completeRegistration = async (payload: CompleteRegistrationRequest): Promise<AuthResponse> => {
  const formData = new FormData();
  formData.append('registration_token', payload.registration_token);
  formData.append('full_name', payload.full_name);
  formData.append('password', payload.password);
  if (payload.avatar) formData.append('avatar', payload.avatar);
  return (await apiClient.post<AuthResponse>('/auth/register/complete/', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })).data;
};

export const loginGoogle = async (token: string): Promise<AuthResponse> =>
  (await apiClient.post<AuthResponse>('/auth/oauth/google/', { token })).data;

export const loginGitHub = async (code: string, redirectUri: string): Promise<AuthResponse> =>
  (await apiClient.post<AuthResponse>('/auth/oauth/github/', { code, redirect_uri: redirectUri })).data;

export const forgotPasswordOTP = async (email: string): Promise<OTPResponse> =>
  (await apiClient.post<OTPResponse>('/auth/password-reset/request-otp/', { email })).data;

export const verifyForgotPasswordOTP = async (
  email: string,
  otpCode: string,
): Promise<PasswordResetVerifyResponse> =>
  (await apiClient.post<PasswordResetVerifyResponse>('/auth/password-reset/verify-otp/', {
    email,
    otp_code: otpCode,
  })).data;

export const resetForgottenPassword = async (resetToken: string, newPassword: string): Promise<OTPResponse> =>
  (await apiClient.post<OTPResponse>('/auth/password-reset/complete/', {
    reset_token: resetToken,
    new_password: newPassword,
  })).data;
