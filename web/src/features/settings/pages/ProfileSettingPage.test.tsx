import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import ProfileSettingPage from "./ProfileSettingPage";
import { renderWithProviders } from "test/renderWithProviders";
import * as profileApi from "@/features/settings/api/profileApi";
import type { UserProfile } from "@/features/settings/types";

vi.mock("@/features/settings/api/profileApi", () => ({
  getProfile: vi.fn(),
  listProfileAvatars: vi.fn(),
  updateProfile: vi.fn(),
  updateProfileAvatar: vi.fn(),
  selectProfileAvatar: vi.fn(),
  deleteAccount: vi.fn(),
  requestPasswordChangeOTP: vi.fn(),
  verifyPasswordChangeOTP: vi.fn(),
  completePasswordChange: vi.fn(),
}));

const mockProfile: UserProfile = {
  email: "ada@example.com",
  full_name: "Ada Lovelace",
  description: "Mathematician and computing pioneer",
  pronouns: "she/her",
  company: "PaaS Corp",
  avatar: null,
  field_of_work: "AI/ML",
  country: "UK",
  tenant_id: "T-TENANT-12345",
  auth_provider: "email",
  date_joined: "2026-01-01T00:00:00Z",
};

describe("ProfileSettingPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(profileApi.getProfile).mockResolvedValue(mockProfile);
    vi.mocked(profileApi.listProfileAvatars).mockResolvedValue({ avatars: [] });
    vi.mocked(profileApi.updateProfile).mockResolvedValue({
      message: "Profile updated successfully",
    });
  });

  it("renders profile information correctly", async () => {
    renderWithProviders(<ProfileSettingPage />);

    expect((await screen.findAllByText("ada@example.com")).length).toBeGreaterThan(0);
    expect(screen.getByDisplayValue("Ada Lovelace")).toBeInTheDocument();
    expect(screen.getByText("T-TENANT")).toBeInTheDocument();
  });

  it("enters edit mode and allows updating full name and saving", async () => {
    const { user } = renderWithProviders(<ProfileSettingPage />);

    expect((await screen.findAllByText("Ada Lovelace")).length).toBeGreaterThan(0);

    const editBtn = screen.getByRole("button", { name: /edit profile/i });
    await user.click(editBtn);

    const fullNameInput = screen.getByDisplayValue("Ada Lovelace");
    await user.clear(fullNameInput);
    await user.type(fullNameInput, "Ada King");

    const saveBtn = screen.getByRole("button", { name: /save/i });
    await user.click(saveBtn);

    await waitFor(() => {
      expect(profileApi.updateProfile).toHaveBeenCalledWith(
        expect.objectContaining({
          full_name: "Ada King",
        }),
        expect.anything(),
      );
    });
  });

  it("cancels edit mode without updating profile", async () => {
    const { user } = renderWithProviders(<ProfileSettingPage />);

    expect(await screen.findByText("Ada Lovelace")).toBeInTheDocument();

    const editBtn = screen.getByRole("button", { name: /edit profile/i });
    await user.click(editBtn);

    const cancelBtn = screen.getByRole("button", { name: /cancel/i });
    await user.click(cancelBtn);

    expect(screen.getByRole("button", { name: /edit profile/i })).toBeInTheDocument();
    expect(profileApi.updateProfile).not.toHaveBeenCalled();
  });
});
