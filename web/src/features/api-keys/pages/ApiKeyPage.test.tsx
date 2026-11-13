import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import ApiKeyPage from "./ApiKeyPage";
import { renderWithProviders } from "test/renderWithProviders";
import * as apiKeysApi from "@/features/api-keys/api/apiKeysApi";
import * as catalogApi from "@/shared/api/catalogApi";
import type { APIKeyRecord } from "@/features/api-keys/types";

const mockNavigate = vi.fn();
vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual("react-router-dom");
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

vi.mock("@/features/api-keys/api/apiKeysApi", () => ({
  listAPIKeys: vi.fn(),
  createAPIKey: vi.fn(),
  updateAPIKey: vi.fn(),
  deleteAPIKey: vi.fn(),
  regenerateAPIKey: vi.fn(),
}));

vi.mock("@/shared/api/catalogApi", () => ({
  listModelProjects: vi.fn(),
}));

const mockKey1: APIKeyRecord = {
  id: "key-1",
  name: "Production Pipeline Key",
  description: "Used by CI/CD worker",
  key_prefix: "paas_live_",
  scope: "all",
  allowed_models: [],
  created_at: "2026-01-01T12:00:00Z",
};

const mockKey2: APIKeyRecord = {
  id: "key-2",
  name: "Fraud Service Key",
  description: "Scoring endpoint access",
  key_prefix: "paas_fraud_",
  scope: "specific",
  allowed_models: ["fraud-detector"],
  created_at: "2026-02-01T12:00:00Z",
};

describe("ApiKeyPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(catalogApi.listModelProjects).mockResolvedValue({
      models: [
        {
          id: "fraud-detector",
          name: "Fraud Detector",
          description: "Detects fraudulent orders",
          model_type: "sklearn",
          framework: "scikit-learn",
          default_version: "v1",
          created_at: "2026-01-01T00:00:00Z",
          versions: [],
        },
      ],
      total: 1,
    } as unknown as Awaited<ReturnType<typeof catalogApi.listModelProjects>>);

    vi.mocked(apiKeysApi.listAPIKeys).mockResolvedValue({
      tenant_id: "tenant-1",
      api_keys: [mockKey1, mockKey2],
    });

    vi.mocked(apiKeysApi.deleteAPIKey).mockResolvedValue({
      message: "API key revoked.",
    });

    vi.mocked(apiKeysApi.regenerateAPIKey).mockResolvedValue({
      ...mockKey1,
      api_key: "paas_live_new_secret_token_12345",
      message: "API key regenerated.",
    });
  });

  it("renders API keys list with names and scopes", async () => {
    renderWithProviders(<ApiKeyPage />);

    expect(
      await screen.findByText("Production Pipeline Key"),
    ).toBeInTheDocument();
    expect(screen.getByText("Fraud Service Key")).toBeInTheDocument();
    expect(screen.getByText("All models")).toBeInTheDocument();
    expect(screen.getByText("Fraud Detector")).toBeInTheDocument();
  });

  it("navigates to create api key page on Create click", async () => {
    const { user } = renderWithProviders(<ApiKeyPage />);

    const createBtn = await screen.findByRole("button", {
      name: /create api key/i,
    });
    await user.click(createBtn);

    expect(mockNavigate).toHaveBeenCalledWith("/dashboard/api-keys/new");
  });

  it("opens delete confirmation and revokes key on confirm", async () => {
    const { user } = renderWithProviders(<ApiKeyPage />);

    expect(
      await screen.findByText("Production Pipeline Key"),
    ).toBeInTheDocument();

    const deleteButtons = screen.getAllByRole("button", {
      name: /delete api key/i,
    });
    await user.click(deleteButtons[0]);

    const confirmBtn = await screen.findByRole("button", {
      name: /delete key/i,
    });
    await user.click(confirmBtn);

    await waitFor(() => {
      expect(apiKeysApi.deleteAPIKey).toHaveBeenCalledWith(
        "key-1",
        expect.anything(),
      );
    });
  });

  it("opens regenerate confirmation and displays new key dialog on confirm", async () => {
    const { user } = renderWithProviders(<ApiKeyPage />);

    expect(
      await screen.findByText("Production Pipeline Key"),
    ).toBeInTheDocument();

    const regenButtons = screen.getAllByRole("button", {
      name: /regenerate api key/i,
    });
    await user.click(regenButtons[0]);

    const confirmBtn = await screen.findByRole("button", {
      name: /regenerate key/i,
    });
    await user.click(confirmBtn);

    await waitFor(() => {
      expect(apiKeysApi.regenerateAPIKey).toHaveBeenCalledWith(
        "key-1",
        expect.anything(),
      );
    });

    expect(
      await screen.findByText("paas_live_new_secret_token_12345"),
    ).toBeInTheDocument();
  });
});
