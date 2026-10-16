import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import { NotificationDropdown } from "./NotificationDropdown";
import { renderWithProviders } from "test/renderWithProviders";
import * as notifApi from "@/features/notifications/api/notificationsApi";
import { createMockNotification } from "test/fixtures/notifications";

const mockNavigate = vi.fn();
vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual("react-router-dom");
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

vi.mock("@/features/notifications/api/notificationsApi", () => ({
  listNotifications: vi.fn(),
  getUnreadCount: vi.fn(),
  markNotificationAsRead: vi.fn(),
  markAllNotificationsAsRead: vi.fn(),
  deleteNotification: vi.fn(),
}));

describe("NotificationDropdown", () => {
  const mockItem = createMockNotification({
    id: "notif-1",
    title: "Deployment Finished",
    is_read: false,
  });

  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(notifApi.getUnreadCount).mockResolvedValue({ unread_count: 3 });
    vi.mocked(notifApi.listNotifications).mockResolvedValue({
      count: 1,
      next: null,
      previous: null,
      results: [mockItem],
    });
    vi.mocked(notifApi.markAllNotificationsAsRead).mockResolvedValue({
      updated: 3,
    });
  });

  it("renders trigger button with unread badge count", async () => {
    renderWithProviders(<NotificationDropdown />);

    expect(await screen.findByText("3")).toBeInTheDocument();
  });

  it("opens dropdown on click and displays notification items", async () => {
    const { user } = renderWithProviders(<NotificationDropdown />);

    const trigger = screen.getByRole("button", { name: /notifications/i });
    await user.click(trigger);

    expect(await screen.findByText("Deployment Finished")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /mark all as read/i }),
    ).toBeInTheDocument();
  });

  it("triggers mark all as read when mark all button is clicked", async () => {
    const { user } = renderWithProviders(<NotificationDropdown />);

    const trigger = screen.getByRole("button", { name: /notifications/i });
    await user.click(trigger);

    const markAllBtn = await screen.findByRole("button", {
      name: /mark all as read/i,
    });
    await user.click(markAllBtn);

    await waitFor(() => {
      expect(notifApi.markAllNotificationsAsRead).toHaveBeenCalled();
    });
  });

  it("navigates to notifications page when View All is clicked", async () => {
    const { user } = renderWithProviders(<NotificationDropdown />);

    const trigger = screen.getByRole("button", { name: /notifications/i });
    await user.click(trigger);

    const viewAllBtn = await screen.findByRole("button", {
      name: /view all/i,
    });
    await user.click(viewAllBtn);

    expect(mockNavigate).toHaveBeenCalledWith("/dashboard/notifications");
  });
});
