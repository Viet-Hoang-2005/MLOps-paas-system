import {
  loginBaseAuth,
  loginGitHub,
  loginGoogle,
  logoutSession,
} from "@/features/auth/api/authApi";
import {
  clearAuthStore,
  getAccessToken,
  getTenantId,
  isAuthenticated,
  setAuthTokens,
} from "@/features/auth/authStore";
import { broadcastLogout, initAuthBroadcast } from "@/features/auth/authSync";
import type { AuthResponse, LoginCredentials } from "@/features/auth/types";
import { getApiErrorMessage } from "@/shared/api/errors";
import { toast } from "@/shared/types/toastStore";
import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

export {
  clearAuthStore,
  getAccessToken,
  getTenantId,
  isAuthenticated,
  setAuthTokens,
};
export const clearAuthTokens = clearAuthStore;
export const getRefreshToken = () => null;

const saveTokens = (access: string, tenantId?: string) => {
  setAuthTokens({ access, tenantId });
};

export function useAuth() {
  const navigate = useNavigate();
  const { t } = useTranslation("auth");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const cleanup = initAuthBroadcast(() => {
      clearAuthStore();
      navigate("/login");
    });
    return cleanup;
  }, [navigate]);

  const handleOAuthSuccess = useCallback(
    (response: AuthResponse, successMessage = t("login.oauthSuccess")) => {
      saveTokens(response.access, response.tenant_id);
      toast.success(successMessage);
      navigate("/dashboard");
    },
    [navigate, t],
  );

  const login = useCallback(
    async (credentials: LoginCredentials) => {
      if (!credentials.email || !credentials.password) {
        toast.warning(t("login.credentialsRequired"));
        return;
      }

      setLoading(true);
      try {
        const response = await loginBaseAuth(credentials);
        saveTokens(response.access, response.tenant_id);
        toast.success(t("login.success"));
        navigate("/dashboard");
      } catch (error) {
        toast.error(getApiErrorMessage(error, t("login.invalidCredentials")));
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
        handleOAuthSuccess(response, t("login.googleSuccess"));
      } catch (error) {
        toast.error(getApiErrorMessage(error, t("login.googleFailed")));
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
        handleOAuthSuccess(response, t("login.githubSuccess"));
      } catch (error) {
        toast.error(getApiErrorMessage(error, t("login.githubFailed")));
        navigate("/login");
      } finally {
        setLoading(false);
      }
    },
    [handleOAuthSuccess, navigate, t],
  );

  const saveAuthTokens = useCallback(
    (
      access: string,
      arg2?: string,
      arg3?: string,
      arg4?: string,
    ) => {
      let redirectTo = "/dashboard";
      let tenantId: string | undefined;

      if (arg2 && arg2.startsWith("/")) {
        redirectTo = arg2;
        tenantId = arg3;
      } else {
        if (arg3 && arg3.startsWith("/")) {
          redirectTo = arg3;
          tenantId = arg4;
        } else {
          tenantId = arg3 || arg4;
        }
      }

      saveTokens(access, tenantId);
      navigate(redirectTo);
    },
    [navigate],
  );

  const logout = useCallback(async () => {
    try {
      await logoutSession();
    } finally {
      clearAuthStore();
      broadcastLogout();
      toast.success(t("login.logoutSuccess"));
      navigate("/login");
    }
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
