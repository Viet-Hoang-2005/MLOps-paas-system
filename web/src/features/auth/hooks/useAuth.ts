import { useCallback, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { loginBaseAuth, loginGitHub, loginGoogle } from '@/features/auth/api/authApi';
import { getApiErrorMessage } from '@/shared/api/errors';
import { toast } from '@/shared/components/toastStore';
import type { AuthResponse, LoginCredentials } from '@/features/auth/types';

export const getAccessToken = () => localStorage.getItem('access_token');
export const getRefreshToken = () => localStorage.getItem('refresh_token');
export const isAuthenticated = () => !!getAccessToken();

const saveTokens = (access: string, refresh: string, tenantId?: string) => {
  localStorage.setItem('access_token', access);
  localStorage.setItem('refresh_token', refresh);
  if (tenantId) {
    localStorage.setItem('tenant_id', tenantId);
  }
};

export const clearAuthTokens = () => {
  localStorage.removeItem('access_token');
  localStorage.removeItem('refresh_token');
  localStorage.removeItem('tenant_id');
};

export function useAuth() {
  const navigate = useNavigate();
  const { t } = useTranslation('auth');
  const [loading, setLoading] = useState(false);

  const handleOAuthSuccess = useCallback(
    (response: AuthResponse, successMessage = t('login.oauthSuccess')) => {
      saveTokens(response.access, response.refresh, response.tenant_id);
      toast.success(successMessage);
      navigate('/dashboard');
    },
    [navigate, t],
  );

  const login = useCallback(
    async (credentials: LoginCredentials) => {
      if (!credentials.email || !credentials.password) {
        toast.warning(t('login.credentialsRequired'));
        return;
      }

      setLoading(true);
      try {
        const response = await loginBaseAuth(credentials);
        saveTokens(response.access, response.refresh, response.tenant_id);
        toast.success(t('login.success'));
        navigate('/dashboard');
      } catch (error) {
        toast.error(getApiErrorMessage(error, t('login.invalidCredentials')));
      } finally {
        setLoading(false);
      }
    },
    [navigate, t],
  );

  const loginWithGoogle = useCallback(
    async (googleToken: string) => {
      setLoading(true);
      try {
        const response = await loginGoogle(googleToken);
        handleOAuthSuccess(response, t('login.googleSuccess'));
      } catch (error) {
        toast.error(getApiErrorMessage(error, t('login.googleFailed')));
      } finally {
        setLoading(false);
      }
    },
    [handleOAuthSuccess, t],
  );

  const loginWithGitHubCode = useCallback(
    async (code: string, redirectUri: string) => {
      setLoading(true);
      try {
        const response = await loginGitHub(code, redirectUri);
        handleOAuthSuccess(response, t('login.githubSuccess'));
      } catch (error) {
        toast.error(getApiErrorMessage(error, t('login.githubFailed')));
        navigate('/login');
      } finally {
        setLoading(false);
      }
    },
    [handleOAuthSuccess, navigate, t],
  );

  const saveAuthTokens = useCallback(
    (access: string, refresh: string, redirectTo = '/dashboard', tenantId?: string) => {
      saveTokens(access, refresh, tenantId);
      navigate(redirectTo);
    },
    [navigate],
  );

  const logout = useCallback(() => {
    clearAuthTokens();
    toast.success(t('login.logoutSuccess'));
    navigate('/login');
  }, [navigate, t]);

  return {
    login,
    logout,
    saveAuthTokens,
    loginWithGoogle,
    loginWithGitHubCode,
    loading,
    isAuthenticated,
  };
}
