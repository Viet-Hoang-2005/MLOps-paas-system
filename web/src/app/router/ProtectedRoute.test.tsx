import * as authApi from "@/features/auth/api/authApi";
import * as authStore from "@/features/auth/authStore";
import { ProtectedRoute } from "@/app/router/ProtectedRoute";
import { renderWithProviders } from "test/renderWithProviders";
import { screen } from "@testing-library/react";
import { Route, Routes } from "react-router-dom";
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
    vi.spyOn(authApi, "refreshSession").mockRejectedValue(new Error("Unauthorized"));

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
});
