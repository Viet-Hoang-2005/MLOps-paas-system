import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import { renderWithProviders } from "test/renderWithProviders";
import Header from "./Header";
import ProfileSettingPage from "@/features/settings/pages/ProfileSettingPage";
import * as api from "@/features/settings/api/profileApi";
import type { UserProfile } from "@/features/settings/types";

vi.mock("@/features/projects/hooks/useModelSelection", () => ({
  useModelSelection: () => ({
    models: [],
    selectedModel: null,
    selectModel: vi.fn(),
  }),
}));
vi.mock("@/features/notifications/components/NotificationDropdown", () => ({
  NotificationDropdown: () => null,
}));
vi.mock("@/features/settings/api/profileApi", async (original) => ({
  ...(await original<typeof import("@/features/settings/api/profileApi")>()),
  getProfile: vi.fn(),
  updateProfileAvatar: vi.fn(),
}));
vi.mock("@/shared/components/CropDialog", () => ({
  CropDialog: ({
    imageSrc,
    onConfirm,
  }: {
    imageSrc: string;
    onConfirm: (file: File) => Promise<void>;
  }) =>
    imageSrc ? (
      <button
        data-testid="confirm-crop"
        onClick={() =>
          void onConfirm(
            new File(["cropped"], "avatar.png", { type: "image/png" }),
          )
        }
      >
        Confirm crop
      </button>
    ) : null,
}));

const original = {
  email: "avatar@example.test",
  full_name: "Avatar Owner",
  avatar: "https://example.test/old.png",
  tenant_id: "T-avatar",
  auth_provider: "email",
  date_joined: "2026-01-01",
  description: "",
  pronouns: "",
  company: "",
  field_of_work: "",
  country: "",
} satisfies UserProfile;

describe("single account avatar in Settings and Header", () => {
  beforeEach(() => {
    vi.mocked(api.getProfile).mockResolvedValue(original);
    vi.stubGlobal(
      "URL",
      class extends URL {
        static createObjectURL() {
          return "blob:avatar-crop";
        }
        static revokeObjectURL() {}
      },
    );
  });
  afterEach(() => vi.unstubAllGlobals());

  it.each(["en", "vi"] as const)(
    "replaces and removes the shared profile avatar in %s",
    async (language) => {
      const { user, container, i18n } = renderWithProviders(
        <>
          <Header onOpenNavigation={vi.fn()} />
          <ProfileSettingPage />
        </>,
        { language },
      );
      const updateLabel = i18n.t("profilePage.updateAvatar", {
        ns: "settings",
      });
      await screen.findByRole("button", { name: updateLabel });
      const oldImages = () =>
        container.querySelectorAll('img[src="https://example.test/old.png"]');
      await waitFor(() => expect(oldImages()).toHaveLength(2));
      await user.click(screen.getByRole("button", { name: updateLabel }));
      expect(
        screen.queryByText(/Previous avatars|Ảnh đại diện trước/),
      ).not.toBeInTheDocument();
      vi.mocked(api.updateProfileAvatar).mockImplementation(() => {
        vi.mocked(api.getProfile).mockResolvedValue({
          ...original,
          avatar: "https://example.test/new.png",
        });
        return Promise.resolve({ message: "Profile updated." });
      });
      await user.upload(
        container.querySelector('input[type="file"]')!,
        new File(["image"], "new.png", { type: "image/png" }),
      );
      await user.click(await screen.findByTestId("confirm-crop"));
      await waitFor(() =>
        expect(
          container.querySelectorAll('img[src="https://example.test/new.png"]'),
        ).toHaveLength(2),
      );
      expect(api.updateProfileAvatar).toHaveBeenCalledWith(
        { avatar: expect.any(File) },
        expect.anything(),
      );
      await user.click(screen.getByRole("button", { name: updateLabel }));
      vi.mocked(api.updateProfileAvatar).mockImplementation(() => {
        vi.mocked(api.getProfile).mockResolvedValue({
          ...original,
          avatar: null,
        });
        return Promise.resolve({ message: "Profile updated." });
      });
      await user.click(
        screen.getByRole("button", {
          name: i18n.t("removeAvatar", { ns: "settings" }),
        }),
      );
      await waitFor(() =>
        expect(
          container.querySelectorAll('img[src="https://example.test/new.png"]'),
        ).toHaveLength(0),
      );
      expect(
        screen.getByRole("button", { name: updateLabel }),
      ).toHaveTextContent("AO");
    },
  );

  it("keeps the current image and crop when upload fails", async () => {
    const { user, container } = renderWithProviders(<ProfileSettingPage />);
    await screen.findByRole("button", { name: "Update avatar" });
    vi.mocked(api.updateProfileAvatar).mockRejectedValue(
      new Error("Storage unavailable"),
    );
    await user.upload(
      container.querySelector('input[type="file"]')!,
      new File(["image"], "new.png", { type: "image/png" }),
    );
    await user.click(await screen.findByTestId("confirm-crop"));
    await waitFor(() => expect(api.updateProfileAvatar).toHaveBeenCalled());
    expect(
      container.querySelector('img[src="https://example.test/old.png"]'),
    ).toBeInTheDocument();
    expect(screen.getByTestId("confirm-crop")).toBeInTheDocument();
  });

  it("keeps the current image when removal fails", async () => {
    const { user, container } = renderWithProviders(<ProfileSettingPage />);
    await user.click(
      await screen.findByRole("button", { name: "Update avatar" }),
    );
    vi.mocked(api.updateProfileAvatar).mockRejectedValue(
      new Error("Storage unavailable"),
    );
    await user.click(screen.getByRole("button", { name: "Remove Avatar" }));
    await waitFor(() =>
      expect(api.updateProfileAvatar).toHaveBeenCalledWith(
        { remove_avatar: true },
        expect.anything(),
      ),
    );
    expect(
      container.querySelector('img[src="https://example.test/old.png"]'),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Remove Avatar" }),
    ).toBeInTheDocument();
  });
});
