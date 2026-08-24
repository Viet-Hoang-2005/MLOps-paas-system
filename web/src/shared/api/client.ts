import axios, { type InternalAxiosRequestConfig } from 'axios';
import { apiBaseURL } from './config';

type RetryableRequestConfig = InternalAxiosRequestConfig & { _retry?: boolean };
type TokenRefreshResponse = { access: string; refresh?: string };

const refreshTokenPath = '/auth/token/refresh/';
const publicAuthPaths = ['/auth/token/', '/auth/oauth/', '/auth/register/', '/auth/password-reset/'];
let refreshPromise: Promise<string> | null = null;

const buildURL = (baseURL: string, path: string) => `${baseURL.replace(/\/+$/, '')}${path}`;
const isPublicAuthRequest = (url = '') => publicAuthPaths.some((path) => url.includes(path));

const clearAuthAndRedirect = () => {
  localStorage.removeItem('access_token');
  localStorage.removeItem('refresh_token');
  localStorage.removeItem('tenant_id');
  if (window.location.pathname !== '/login') window.location.href = '/login';
};

export const refreshAccessToken = () => {
  const refreshToken = localStorage.getItem('refresh_token');
  if (!refreshToken) return Promise.reject(new Error('Missing refresh token.'));

  if (!refreshPromise) {
    refreshPromise = axios
      .post<TokenRefreshResponse>(
        buildURL(apiBaseURL, refreshTokenPath),
        { refresh: refreshToken },
        { headers: { 'Content-Type': 'application/json' } },
      )
      .then((response) => {
        localStorage.setItem('access_token', response.data.access);
        if (response.data.refresh) localStorage.setItem('refresh_token', response.data.refresh);
        return response.data.access;
      })
      .finally(() => { refreshPromise = null; });
  }
  return refreshPromise;
};

export const apiClient = axios.create({
  baseURL: apiBaseURL,
  headers: { 'Content-Type': 'application/json' },
});

apiClient.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('access_token');
    if (token) config.headers.Authorization = `Bearer ${token}`;
    return config;
  },
  (error: unknown) => Promise.reject(error),
);

apiClient.interceptors.response.use(
  (response) => response,
  async (error: unknown) => {
    if (!axios.isAxiosError(error) || error.response?.status !== 401) return Promise.reject(error);
    const originalRequest = error.config as RetryableRequestConfig | undefined;
    if (!originalRequest || originalRequest._retry || isPublicAuthRequest(originalRequest.url)) {
      if (originalRequest?._retry) clearAuthAndRedirect();
      return Promise.reject(error);
    }
    originalRequest._retry = true;
    try {
      originalRequest.headers.Authorization = `Bearer ${await refreshAccessToken()}`;
      return apiClient(originalRequest);
    } catch (refreshError) {
      clearAuthAndRedirect();
      return Promise.reject(refreshError);
    }
  },
);
