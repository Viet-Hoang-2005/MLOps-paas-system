export interface LoginCredentials {
  email: string;
  password: string;
}

export interface SignUpRequest {
  email: string;
}

export interface OTPVerifyRequest {
  email: string;
  otp_code: string;
}

export interface CompleteRegistrationRequest {
  registration_token: string;
  full_name: string;
  avatar?: File | null;
  password: string;
}

export interface ForgotPasswordRequest {
  email: string;
}

export interface PasswordResetVerifyRequest {
  email: string;
  otp_code: string;
}

export interface PasswordResetCompleteRequest {
  reset_token: string;
  new_password: string;
}

export interface AuthResponse {
  message: string;
  access: string;
  refresh: string;
  tenant_id: string;
  is_new_user?: boolean;
}

export interface OTPResponse {
  message: string;
  email: string;
}

export interface OTPVerifyResponse {
  message: string;
  registration_token: string;
}

export interface PasswordResetVerifyResponse {
  message: string;
  reset_token: string;
}
