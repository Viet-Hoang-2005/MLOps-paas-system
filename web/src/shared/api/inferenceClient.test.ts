import * as authSession from "@/shared/api/authSession";
import * as clientModule from "@/shared/api/client";
import { inferenceClient } from "@/shared/api/inferenceClient";
import axios, { type AxiosResponse, type InternalAxiosRequestConfig } from "axios";
import { beforeEach, describe, expect, it, vi } from "vitest";

describe("inferenceClient - Public/Private, Token Injection & Single Refresh", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    authSession.clearAuthSession();
  });

  it("should enforce withCredentials: false and 30s timeout defaults", () => {
    expect(inferenceClient.defaults.withCredentials).toBe(false);
    expect(inferenceClient.defaults.timeout).toBe(30_000);
  });

  it("should omit Authorization header for public requests when no token is stored", async () => {
    vi.spyOn(authSession, "getAccessToken").mockReturnValue(null);

    let capturedConfig: InternalAxiosRequestConfig | undefined;
    inferenceClient.defaults.adapter = async (config) => {
      capturedConfig = config;
      return {
        data: { prediction: [1] },
        status: 200,
        statusText: "OK",
        headers: {},
        config,
      } as AxiosResponse;
    };

    await inferenceClient.post("http://gateway/predict", { data: [[1]] });
    expect(capturedConfig?.headers.Authorization).toBeUndefined();
    expect(capturedConfig?.withCredentials).toBe(false);
  });

  it("should inject Bearer token for private requests when token exists", async () => {
    vi.spyOn(authSession, "getAccessToken").mockReturnValue("access-token-1");

    let capturedConfig: InternalAxiosRequestConfig | undefined;
    inferenceClient.defaults.adapter = async (config) => {
      capturedConfig = config;
      return {
        data: { prediction: [1] },
        status: 200,
        statusText: "OK",
        headers: {},
        config,
      } as AxiosResponse;
    };

    await inferenceClient.post("http://gateway/predict", { data: [[1]] });
    expect(capturedConfig?.headers.Authorization).toBe("Bearer access-token-1");
  });

  it("should retry with new token on 401 'Token has expired'", async () => {
    let callCount = 0;
    let currentToken = "initial-token";
    vi.spyOn(authSession, "getAccessToken").mockImplementation(() => currentToken);
    const refreshSpy = vi
      .spyOn(clientModule, "refreshAccessToken")
      .mockImplementation(async () => {
        currentToken = "refreshed-token";
        return currentToken;
      });

    const authHeaders: (string | undefined)[] = [];
    inferenceClient.defaults.adapter = async (config) => {
      callCount++;
      authHeaders.push(
        config.headers.Authorization
          ? String(config.headers.Authorization)
          : undefined,
      );
      if (callCount === 1) {
        throw new axios.AxiosError("Expired", "ERR_BAD_RESPONSE", config, {}, {
          status: 401,
          statusText: "Unauthorized",
          data: { detail: "Unauthorized: Token has expired" },
          headers: {},
          config,
        });
      }
      return {
        data: { prediction: [42] },
        status: 200,
        statusText: "OK",
        headers: {},
        config,
      } as AxiosResponse;
    };

    const res = await inferenceClient.post("http://gateway/predict", { data: [[1]] });
    expect(res.status).toBe(200);
    expect(res.data).toEqual({ prediction: [42] });
    expect(refreshSpy).toHaveBeenCalledTimes(1);
    expect(authHeaders[0]).toBe("Bearer initial-token");
    expect(authHeaders[1]).toBe("Bearer refreshed-token");
  });

  it("should not retry on other errors like 403, 500, or invalid token", async () => {
    vi.spyOn(authSession, "getAccessToken").mockReturnValue("token");
    const refreshSpy = vi.spyOn(clientModule, "refreshAccessToken");

    for (const code of [403, 500, 504]) {
      inferenceClient.defaults.adapter = async (config) => {
        throw new axios.AxiosError("Error", "ERR_BAD_RESPONSE", config, {}, {
          status: code,
          statusText: "Error",
          data: { detail: "Unauthorized: Invalid token" },
          headers: {},
          config,
        });
      };

      await expect(
        inferenceClient.post("http://gateway/predict", { data: [[1]] }),
      ).rejects.toThrow();
    }

    expect(refreshSpy).not.toHaveBeenCalled();
  });
});
