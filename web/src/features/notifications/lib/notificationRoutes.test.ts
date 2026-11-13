import { describe, expect, it } from "vitest";
import { getNotificationDestination } from "./notificationRoutes";
import type { NotificationItem } from "@/features/notifications/types";

describe("getNotificationDestination", () => {
  const baseNotification: NotificationItem = {
    id: "notif-1",
    title: "Test Notification",
    message: "Test message",
    type: "project",
    level: "info",
    is_read: false,
    created_at: new Date().toISOString(),
  };

  it("navigates project notifications to /dashboard/projects", () => {
    const notif: NotificationItem = {
      ...baseNotification,
      type: "project",
      link: "/dashboard/projects/proj-123/overview",
      metadata: { project_id: "proj-123" },
    };
    expect(getNotificationDestination(notif)).toBe("/dashboard/projects");
  });

  it("navigates training notifications to /dashboard/projects/<id>/training", () => {
    const notif: NotificationItem = {
      ...baseNotification,
      type: "training",
      link: "/dashboard/projects/proj-123/training",
      metadata: { project_id: "proj-123" },
    };
    expect(getNotificationDestination(notif)).toBe(
      "/dashboard/projects/proj-123/training",
    );
  });

  it("navigates build (packaging) notifications to /dashboard/projects/<id>/deployment (without s)", () => {
    const notif: NotificationItem = {
      ...baseNotification,
      type: "build",
      // Even if legacy link had /deployments with s
      link: "/dashboard/projects/proj-123/deployments",
    };
    expect(getNotificationDestination(notif)).toBe(
      "/dashboard/projects/proj-123/deployment",
    );
  });

  it("navigates deployment notifications to /dashboard/projects/<id>/deployment", () => {
    const notif: NotificationItem = {
      ...baseNotification,
      type: "deployment",
      metadata: { project_id: "proj-456" },
    };
    expect(getNotificationDestination(notif)).toBe(
      "/dashboard/projects/proj-456/deployment",
    );
  });

  it("navigates drift notifications to /dashboard/projects/<id>/monitoring", () => {
    const notif: NotificationItem = {
      ...baseNotification,
      type: "drift",
      link: "/dashboard/projects/proj-789/evolution",
      metadata: { project_id: "proj-789" },
    };
    expect(getNotificationDestination(notif)).toBe(
      "/dashboard/projects/proj-789/monitoring",
    );
  });

  it("navigates alert notifications to /dashboard/projects/<id>/overview", () => {
    const notif: NotificationItem = {
      ...baseNotification,
      type: "alert",
      metadata: { project_id: "proj-alert-1" },
    };
    expect(getNotificationDestination(notif)).toBe(
      "/dashboard/projects/proj-alert-1/overview",
    );
  });

  it("falls back to generic routes when project_id is not present", () => {
    expect(
      getNotificationDestination({ ...baseNotification, type: "training" }),
    ).toBe("/dashboard/training");
    expect(
      getNotificationDestination({ ...baseNotification, type: "build" }),
    ).toBe("/dashboard/deployment");
    expect(
      getNotificationDestination({ ...baseNotification, type: "deployment" }),
    ).toBe("/dashboard/deployment");
    expect(
      getNotificationDestination({ ...baseNotification, type: "drift" }),
    ).toBe("/dashboard/monitoring");
    expect(
      getNotificationDestination({ ...baseNotification, type: "alert" }),
    ).toBe("/dashboard/overview");
  });
});
