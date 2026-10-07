import axios, { type InternalAxiosRequestConfig } from "axios";
import { getAccessToken } from "./authSession";
import { refreshAccessToken } from "./client";

type InferenceRequest = InternalAxiosRequestConfig & { _retry?: boolean };

export const inferenceClient = axios.create({
  withCredentials: false,
  timeout: 30_000,
  headers: { "Content-Type": "application/json" },
});

inferenceClient.interceptors.request.use((config) => {
  const token = getAccessToken();
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

inferenceClient.interceptors.response.use(
  (response) => response,
  async (error: unknown) => {
    if (!axios.isAxiosError(error)) return Promise.reject(error);
    const request = error.config as InferenceRequest | undefined;
    if (
      !request ||
      request._retry ||
      error.response?.status !== 401 ||
      error.response.data?.detail !== "Unauthorized: Token has expired"
    )
      return Promise.reject(error);
    request._retry = true;
    const access = await refreshAccessToken();
    request.headers.Authorization = `Bearer ${access}`;
    return inferenceClient(request);
  },
);
