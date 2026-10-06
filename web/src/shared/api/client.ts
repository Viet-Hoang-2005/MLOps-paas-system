import {
  clearAuthStore,
  getAccessToken,
  setAuthTokens,
} from "@/features/auth/authStore";
import { broadcastLogout, runWithRefreshLock } from "@/features/auth/authSync";
import axios, { type InternalAxiosRequestConfig } from "axios";
import { apiBaseURL } from "./config";

type RetryableRequestConfig = InternalAxiosRequestConfig & { _retry?: boolean };
type TokenRefreshResponse = {
  access: string;
  refresh?: string;
  tenant_id?: string;
};

const refreshTokenPath = "/auth/token/refresh/";
const publicAuthPaths = [
  "/auth/token/",
  "/auth/oauth/",
  "/auth/register/",
  "/auth/password-reset/",
  "/auth/logout/",
];
let refreshPromise: Promise<string> | null = null;

const buildURL = (baseURL: string, path: string) =>
  `${baseURL.replace(/\/+$/, "")}${path}`;
const isPublicAuthRequest = (url = "") =>
  publicAuthPaths.some((path) => url.includes(path));

export const clearAuthAndRedirect = () => {
  clearAuthStore();
  broadcastLogout();
  if (typeof window !== "undefined" && window.location.pathname !== "/login") {
    window.location.href = "/login";
  }
};

export const refreshAccessToken = (): Promise<string> => {
  if (!refreshPromise) {
    refreshPromise = runWithRefreshLock(async () => {
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
      const newAccess = response.data.access;
      setAuthTokens({
        access: newAccess,
        tenantId: response.data.tenant_id,
      });
      return newAccess;
    }).finally(() => {
      refreshPromise = null;
    });
  }
  return refreshPromise;
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
    const token = getAccessToken();
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
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
  (error: unknown) => Promise.reject(error),
);

apiClient.interceptors.response.use(
  (response) => response,
  async (error: unknown) => {
    if (!axios.isAxiosError(error) || error.response?.status !== 401) {
      return Promise.reject(error);
    }
    const originalRequest = error.config as RetryableRequestConfig | undefined;
    if (
      !originalRequest ||
      originalRequest._retry ||
      isPublicAuthRequest(originalRequest.url)
    ) {
      if (originalRequest?._retry) {
        clearAuthAndRedirect();
      }
      return Promise.reject(error);
    }
    originalRequest._retry = true;
    try {
      const newAccess = await refreshAccessToken();
      originalRequest.headers.Authorization = `Bearer ${newAccess}`;
      return apiClient(originalRequest);
    } catch (refreshError) {
      clearAuthAndRedirect();
      return Promise.reject(refreshError);
    }
  },
);
