import { apiClient } from "@/shared/api/client";
import * as authSession from "@/shared/api/authSession";
import axios, { type AxiosResponse, type InternalAxiosRequestConfig } from "axios";
import { beforeEach, describe, expect, it, vi } from "vitest";

describe("apiClient Interceptors & Token Handling", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    authSession.clearAuthSession();
  });

  it("should inject Bearer token into headers when token exists", async () => {
    vi.spyOn(authSession, "getAccessToken").mockReturnValue("valid-token-123");

    let capturedConfig: InternalAxiosRequestConfig | undefined;
    apiClient.defaults.adapter = async (config) => {
      capturedConfig = config;
      return {
        data: { success: true },
        status: 200,
        statusText: "OK",
        headers: {},
        config,
      } as AxiosResponse;
    };

    const response = await apiClient.get("/test/endpoint");
    expect(response.status).toBe(200);
    expect(capturedConfig?.headers.Authorization).toBe("Bearer valid-token-123");
    expect(capturedConfig?.headers["X-Requested-With"]).toBe("XMLHttpRequest");
  });

  it("should omit Authorization header when no token is present", async () => {
    vi.spyOn(authSession, "getAccessToken").mockReturnValue(null);

    let capturedConfig: InternalAxiosRequestConfig | undefined;
    apiClient.defaults.adapter = async (config) => {
      capturedConfig = config;
      return {
        data: { success: true },
        status: 200,
        statusText: "OK",
        headers: {},
        config,
      } as AxiosResponse;
    };

    await apiClient.get("/public/endpoint");
    expect(capturedConfig?.headers.Authorization).toBeUndefined();
  });

  it("should remove Content-Type header when request payload is FormData", async () => {
    vi.spyOn(authSession, "getAccessToken").mockReturnValue("test-token");

    let capturedHeaders: Record<string, unknown> | undefined;
    apiClient.defaults.adapter = async (config) => {
      capturedHeaders = config.headers ? { ...config.headers } : undefined;
      return {
        data: { uploaded: true },
        status: 200,
        statusText: "OK",
        headers: {},
        config,
      } as AxiosResponse;
    };

    const formData = new FormData();
    formData.append("file", "dummy-content");

    await apiClient.post("/upload", formData);
    expect(capturedHeaders?.["Content-Type"]).not.toBe("application/json");
  });

  it("should pass through non-401 errors without attempting refresh", async () => {
    apiClient.defaults.adapter = async (config) => {
      throw new axios.AxiosError("Bad Request", "ERR_BAD_REQUEST", config, {}, {
        status: 400,
        statusText: "Bad Request",
        data: { detail: "Invalid input" },
        headers: {},
        config,
      });
    };

    await expect(apiClient.get("/invalid")).rejects.toThrow();
  });
});
