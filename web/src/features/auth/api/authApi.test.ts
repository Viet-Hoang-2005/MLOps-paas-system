import * as authApi from "@/features/auth/api/authApi";
import { apiClient } from "@/shared/api/client";
import { beforeEach, describe, expect, it, vi } from "vitest";

describe("authApi Network Calls & Responses", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("should post credentials to /auth/token/ for base auth login", async () => {
    const mockPost = vi.spyOn(apiClient, "post").mockResolvedValueOnce({
      data: {
        access: "mock-access-token",
        tenant_id: "tenant-1",
        user: { id: "user-1", email: "user@example.com" },
      },
    });

    const res = await authApi.loginBaseAuth({
      email: "user@example.com",
      password: "secretpassword",
    });

    expect(mockPost).toHaveBeenCalledWith("/auth/token/", {
      email: "user@example.com",
      password: "secretpassword",
    });
    expect(res.access).toBe("mock-access-token");
    expect(res.tenant_id).toBe("tenant-1");
  });

  it("should post oauth token to /auth/oauth/google/ for Google login", async () => {
    const mockPost = vi.spyOn(apiClient, "post").mockResolvedValueOnce({
      data: {
        access: "google-access-token",
        tenant_id: "tenant-2",
        user: { id: "user-2", email: "google@example.com" },
      },
    });

    const res = await authApi.loginGoogle("google-id-token");

    expect(mockPost).toHaveBeenCalledWith("/auth/oauth/google/", {
      token: "google-id-token",
    });
    expect(res.access).toBe("google-access-token");
  });

  it("should call /auth/logout/ on logoutSession", async () => {
    const mockPost = vi.spyOn(apiClient, "post").mockResolvedValueOnce({
      data: { message: "Logged out successfully" },
    });

    const res = await authApi.logoutSession();
    expect(mockPost).toHaveBeenCalledWith("/auth/logout/", {});
    expect(res.message).toBe("Logged out successfully");
  });
});
