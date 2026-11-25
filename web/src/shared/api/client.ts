import {
  broadcastLogout,
  runWithRefreshLock,
} from "@/shared/api/authCoordination";
import {
  clearAuthSession,
  getAccessToken,
  getAuthSessionVersion,
  setAuthSession,
} from "@/shared/api/authSession";
import axios, { type InternalAxiosRequestConfig } from "axios";
import { apiBaseURL } from "./config";
import { isInvalidRefreshSession, SessionChangedError } from "./authErrors";

export type RetryableRequestConfig = InternalAxiosRequestConfig & {
  _retry?: boolean;
  authSessionVersion?: number;
};
type TokenRefreshResponse = {
  access: string;
  tenant_id: string;
};

const refreshTokenPath = "/auth/token/refresh/";
const publicAuthPaths = [
  "/auth/token/",
  "/auth/oauth/",
  "/auth/register/",
  "/auth/password-reset/",
  "/auth/logout/",
];
let pendingRefresh: { version: number; promise: Promise<string> } | null = null;

const buildURL = (baseURL: string, path: string) =>
  `${baseURL.replace(/\/+$/, "")}${path}`;
const isPublicAuthRequest = (url = "") =>
  publicAuthPaths.some((path) => url.includes(path));

export const clearAuthAndRedirect = () => {
  clearAuthSession();
  broadcastLogout();
  if (typeof window !== "undefined" && window.location.pathname !== "/login") {
    window.location.href = "/login";
  }
};

export const assertCurrentSession = (version: number | undefined): void => {
  if (version !== getAuthSessionVersion()) {
    throw new SessionChangedError();
  }
};

export const attachSessionToken = (config: RetryableRequestConfig) => {
  if (config._retry) {
    // Axios runs this interceptor again, after the response interceptor schedules a retry.
    assertCurrentSession(config.authSessionVersion);
  }
  const token = getAccessToken();
  if (token) {
    config.authSessionVersion = getAuthSessionVersion();
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
};

export const refreshAccessToken = (): Promise<string> => {
  const version = getAuthSessionVersion();
  if (pendingRefresh?.version === version) return pendingRefresh.promise;

  const promise = runWithRefreshLock(async () => {
    assertCurrentSession(version);
    const response = await axios.post<TokenRefreshResponse>(
      buildURL(apiBaseURL, refreshTokenPath),
      {},
      {
        withCredentials: true,
        headers: {
          "Content-Type": "application/json",
          "X-Requested-With": "XMLHttpRequest",
        },
      },
    );
    assertCurrentSession(version);
    const { access, tenant_id: tenantId } = response.data;
    if (typeof tenantId !== "string" || !tenantId) {
      throw new SessionChangedError();
    }
    setAuthSession({ access, tenantId }, { refresh: true });
    return access;
  }).finally(() => {
    if (pendingRefresh?.promise === promise) pendingRefresh = null;
  });
  pendingRefresh = { version, promise };
  return promise;
};

export const apiClient = axios.create({
  baseURL: apiBaseURL,
  withCredentials: true,
  headers: {
    "Content-Type": "application/json",
    "X-Requested-With": "XMLHttpRequest",
  },
});

apiClient.interceptors.request.use(
  (config) => {
    attachSessionToken(config);
    if (!config.headers["X-Requested-With"]) {
      config.headers["X-Requested-With"] = "XMLHttpRequest";
    }
    if (config.data instanceof FormData) {
      if (typeof config.headers?.delete === "function") {
        config.headers.delete("Content-Type");
      } else if (config.headers) {
        delete config.headers["Content-Type"];
      }
    }
    return config;
  },
  (error: unknown) =>
    Promise.reject(error instanceof Error ? error : new Error(String(error))),
);

apiClient.interceptors.response.use(
  (response) => response,
  async (error: unknown) => {
    if (!axios.isAxiosError(error) || error.response?.status !== 401) {
      return Promise.reject(
        error instanceof Error ? error : new Error(String(error)),
      );
    }
    const originalRequest = error.config as RetryableRequestConfig | undefined;
    if (
      !originalRequest ||
      originalRequest.authSessionVersion === undefined ||
      isPublicAuthRequest(originalRequest.url)
    ) {
      return Promise.reject(error);
    }
    const { authSessionVersion } = originalRequest;
    assertCurrentSession(authSessionVersion);
    if (originalRequest._retry) {
      clearAuthAndRedirect();
      return Promise.reject(error);
    }
    originalRequest._retry = true;
    try {
      await refreshAccessToken();
      assertCurrentSession(authSessionVersion);
      return apiClient(originalRequest);
    } catch (refreshError: unknown) {
      assertCurrentSession(authSessionVersion);
      if (isInvalidRefreshSession(refreshError)) {
        clearAuthAndRedirect();
      }
      return Promise.reject(
        refreshError instanceof Error
          ? refreshError
          : new Error(String(refreshError)),
      );
    }
  },
);
