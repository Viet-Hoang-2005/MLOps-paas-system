import * as authApi from "@/features/auth/api/authApi";
import * as authStore from "@/features/auth/authStore";
import { ProtectedRoute } from "@/app/router/ProtectedRoute";
import { renderWithProviders } from "test/renderWithProviders";
import { screen } from "@testing-library/react";
import { Route, Routes } from "react-router-dom";
import axios, { type AxiosResponse } from "axios";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

describe("ProtectedRoute Component", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("should render protected content when user is already authenticated", () => {
    vi.spyOn(authStore, "isAuthenticated").mockReturnValue(true);

    renderWithProviders(
      <ProtectedRoute>
        <div>Protected Dashboard Content</div>
      </ProtectedRoute>,
    );

    expect(screen.getByText("Protected Dashboard Content")).toBeInTheDocument();
  });

  it("should redirect to /login when unauthenticated and refreshSession fails", async () => {
    vi.spyOn(authStore, "isAuthenticated").mockReturnValue(false);
    vi.spyOn(authApi, "refreshSession").mockRejectedValue(new axios.AxiosError(
      "Unauthorized", "ERR_BAD_REQUEST", undefined, undefined,
      { status: 401, data: {} } as AxiosResponse,
    ));

    renderWithProviders(
      <Routes>
        <Route
          path="/dashboard"
          element={
            <ProtectedRoute>
              <div>Protected Dashboard Content</div>
            </ProtectedRoute>
          }
        />
        <Route path="/login" element={<div>Login Page</div>} />
      </Routes>,
      { initialEntries: ["/dashboard"] },
    );

    const loginPage = await screen.findByText("Login Page");
    expect(loginPage).toBeInTheDocument();
    expect(screen.queryByText("Protected Dashboard Content")).not.toBeInTheDocument();
  });

  it("should render protected content when refreshSession succeeds", async () => {
    vi.spyOn(authStore, "isAuthenticated").mockReturnValue(false);
    vi.spyOn(authApi, "refreshSession").mockResolvedValue("new-token");

    renderWithProviders(
      <Routes>
        <Route
          path="/dashboard"
          element={
            <ProtectedRoute>
              <div>Protected Dashboard Content</div>
            </ProtectedRoute>
          }
        />
      </Routes>,
      { initialEntries: ["/dashboard"] },
    );

    const content = await screen.findByText("Protected Dashboard Content");
    expect(content).toBeInTheDocument();
  });

  it.each([500, 502, 503, 504, 429, 403, "network", "timeout"])(
    "blocks protected content without logging out when refresh fails with %s and allows retry",
    async (failure) => {
      vi.spyOn(authStore, "isAuthenticated").mockReturnValue(false);
      const clear = vi.spyOn(authStore, "clearAuthStore");
      const refresh = vi.spyOn(authApi, "refreshSession").mockRejectedValueOnce(
        new axios.AxiosError(
          "Unavailable", failure === "timeout" ? "ECONNABORTED" : "ERR_NETWORK",
          undefined, undefined,
          typeof failure === "number"
            ? { status: failure, data: { error: { code: "permission_denied" } } } as AxiosResponse
            : undefined,
        ),
      );
      renderWithProviders(
        <Routes>
          <Route path="/dashboard" element={<ProtectedRoute><div>Protected content</div></ProtectedRoute>} />
          <Route path="/login" element={<div>Login Page</div>} />
        </Routes>,
        { initialEntries: ["/dashboard?project=keep-me"] },
      );

      expect(await screen.findByRole("alert")).toHaveTextContent("Unable to verify your session");
      expect(screen.queryByText("Login Page")).not.toBeInTheDocument();
      expect(screen.queryByText("Protected content")).not.toBeInTheDocument();
      expect(clear).not.toHaveBeenCalled();
      refresh.mockResolvedValueOnce("new-access");
      await userEvent.setup().click(screen.getByRole("button", { name: "Retry" }));
      expect(await screen.findByText("Protected content")).toBeInTheDocument();
      expect(refresh).toHaveBeenCalledTimes(2);
    },
  );

  it.each(["authentication_failed", "token_not_valid"])(
    "redirects to login for DRF 403 authentication failure %s",
    async (code) => {
      vi.spyOn(authStore, "isAuthenticated").mockReturnValue(false);
      vi.spyOn(authApi, "refreshSession").mockRejectedValue(new axios.AxiosError(
        "Invalid session", "ERR_BAD_REQUEST", undefined, undefined,
        { status: 403, data: { error: { code } } } as AxiosResponse,
      ));
      renderWithProviders(
        <Routes>
          <Route path="/dashboard" element={<ProtectedRoute><div>Protected content</div></ProtectedRoute>} />
          <Route path="/login" element={<div>Login Page</div>} />
        </Routes>,
        { initialEntries: ["/dashboard"] },
      );
      expect(await screen.findByText("Login Page")).toBeInTheDocument();
    },
  );
});
