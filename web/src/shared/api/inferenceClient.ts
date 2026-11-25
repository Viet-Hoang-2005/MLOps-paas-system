import axios from "axios";
import {
  assertCurrentSession,
  attachSessionToken,
  refreshAccessToken,
  type RetryableRequestConfig,
} from "./client";

export const inferenceClient = axios.create({
  withCredentials: false,
  timeout: 75_000,
  headers: { "Content-Type": "application/json" },
});

inferenceClient.interceptors.request.use(attachSessionToken);

inferenceClient.interceptors.response.use(
  (response) => response,
  async (error: unknown) => {
    if (!axios.isAxiosError(error)) {
      return Promise.reject(
        error instanceof Error ? error : new Error(String(error)),
      );
    }
    const request = error.config as RetryableRequestConfig | undefined;
    if (
      !request ||
      request.authSessionVersion === undefined ||
      request._retry ||
      error.response?.status !== 401 ||
      error.response.data?.detail !== "Unauthorized: Token has expired"
    )
      return Promise.reject(error);
    assertCurrentSession(request.authSessionVersion);
    request._retry = true;
    await refreshAccessToken();
    assertCurrentSession(request.authSessionVersion);
    return inferenceClient(request);
  },
);
