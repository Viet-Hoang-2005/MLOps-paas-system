import { apiClient } from "@/shared/api/client";
import * as authSession from "@/shared/api/authSession";
import * as authCoordination from "@/shared/api/authCoordination";
import axios, {
  type AxiosResponse,
  type InternalAxiosRequestConfig,
} from "axios";
import { beforeEach, describe, expect, it, vi } from "vitest";

describe("apiClient Interceptors & Token Handling", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    authSession.clearAuthSession();
  });

  it("should inject Bearer token into headers when token exists", async () => {
    vi.spyOn(authSession, "getAccessToken").mockReturnValue("valid-token-123");

    let capturedConfig: InternalAxiosRequestConfig | undefined;
    apiClient.defaults.adapter = (config) => {
      capturedConfig = config;
      return Promise.resolve({
        data: { success: true },
        status: 200,
        statusText: "OK",
        headers: {},
        config,
      } as AxiosResponse);
    };

    const response = await apiClient.get("/test/endpoint");
    expect(response.status).toBe(200);
    expect(capturedConfig?.headers.Authorization).toBe(
      "Bearer valid-token-123",
    );
    expect(capturedConfig?.headers["X-Requested-With"]).toBe("XMLHttpRequest");
  });

  it("should omit Authorization header when no token is present", async () => {
    vi.spyOn(authSession, "getAccessToken").mockReturnValue(null);

    let capturedConfig: InternalAxiosRequestConfig | undefined;
    apiClient.defaults.adapter = (config) => {
      capturedConfig = config;
      return Promise.resolve({
        data: { success: true },
        status: 200,
        statusText: "OK",
        headers: {},
        config,
      } as AxiosResponse);
    };

    await apiClient.get("/public/endpoint");
    expect(capturedConfig?.headers.Authorization).toBeUndefined();
  });

  it("should remove Content-Type header when request payload is FormData", async () => {
    vi.spyOn(authSession, "getAccessToken").mockReturnValue("test-token");

    let capturedHeaders: Record<string, unknown> | undefined;
    apiClient.defaults.adapter = (config) => {
      capturedHeaders = config.headers ? { ...config.headers } : undefined;
      return Promise.resolve({
        data: { uploaded: true },
        status: 200,
        statusText: "OK",
        headers: {},
        config,
      } as AxiosResponse);
    };

    const formData = new FormData();
    formData.append("file", "dummy-content");

    await apiClient.post("/upload", formData);
    expect(capturedHeaders?.["Content-Type"]).not.toBe("application/json");
  });

  it("should pass through non-401 errors without attempting refresh", async () => {
    apiClient.defaults.adapter = (config) => {
      return Promise.reject(
        new axios.AxiosError(
          "Bad Request",
          "ERR_BAD_REQUEST",
          config,
          {},
          {
            status: 400,
            statusText: "Bad Request",
            data: { detail: "Invalid input" },
            headers: {},
            config,
          },
        ),
      );
    };

    await expect(apiClient.get("/invalid")).rejects.toThrow();
  });

  it.each([500, 502, 503, 504, 429, 403, "timeout", "network"])(
    "preserves the session and other tabs when refresh fails with %s",
    async (failure) => {
      authSession.setAuthSession({ access: "old-access", tenantId: "tenant" });
      const broadcast = vi.spyOn(authCoordination, "broadcastLogout");
      const refreshError = new axios.AxiosError(
        "Refresh unavailable",
        failure === "timeout" ? "ECONNABORTED" : "ERR_NETWORK",
        undefined,
        undefined,
        typeof failure === "number"
          ? ({
              status: failure,
              data: { error: { code: "permission_denied" } },
            } as AxiosResponse)
          : undefined,
      );
      const refresh = vi
        .spyOn(axios, "post")
        .mockRejectedValueOnce(refreshError);
      apiClient.defaults.adapter = (config) => {
        if (config.headers.Authorization === "Bearer new-access") {
          return Promise.resolve({
            data: {},
            status: 200,
            statusText: "OK",
            headers: {},
            config,
          });
        }
        return Promise.reject(
          new axios.AxiosError(
            "Unauthorized",
            "ERR_BAD_REQUEST",
            config,
            {},
            {
              status: 401,
              statusText: "Unauthorized",
              data: {},
              headers: {},
              config,
            },
          ),
        );
      };

      await expect(apiClient.get("/protected")).rejects.toBe(refreshError);
      expect(authSession.getAccessToken()).toBe("old-access");
      expect(authSession.getTenantId()).toBe("tenant");
      expect(broadcast).not.toHaveBeenCalled();

      // The next user action can refresh successfully without signing in again.
      refresh.mockResolvedValueOnce({
        data: { access: "new-access", tenant_id: "tenant" },
      });
      expect((await apiClient.get("/protected")).status).toBe(200);
      expect(authSession.getAccessToken()).toBe("new-access");
    },
  );

  it("does not refresh or clear the session for a business API 503", async () => {
    authSession.setAuthSession({ access: "access", tenantId: "tenant" });
    const refresh = vi.spyOn(axios, "post");
    const broadcast = vi.spyOn(authCoordination, "broadcastLogout");
    apiClient.defaults.adapter = (config) =>
      Promise.reject(
        new axios.AxiosError(
          "Unavailable",
          "ERR_BAD_RESPONSE",
          config,
          {},
          {
            status: 503,
            statusText: "Unavailable",
            data: {},
            headers: {},
            config,
          },
        ),
      );
    await expect(apiClient.get("/protected")).rejects.toThrow();
    expect(authSession.getAccessToken()).toBe("access");
    expect(refresh).not.toHaveBeenCalled();
    expect(broadcast).not.toHaveBeenCalled();
  });
});
