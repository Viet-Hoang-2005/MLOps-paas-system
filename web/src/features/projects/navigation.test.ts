import { projectSelectionPath } from "@/features/projects/navigation";
import { describe, expect, it } from "vitest";

describe("Projects Navigation - projectSelectionPath", () => {
  const sections = [
    "overview",
    "deployment",
    "monitoring",
    "training",
    "evolution",
  ] as const;

  it("should preserve active section when switching projects from an existing project path", () => {
    for (const section of sections) {
      expect(
        projectSelectionPath(`/dashboard/projects/old-proj/${section}`, "new-proj"),
      ).toBe(`/dashboard/projects/new-proj/${section}`);
    }
  });

  it("should preserve section when navigating from bare dashboard section path", () => {
    for (const section of sections) {
      expect(projectSelectionPath(`/dashboard/${section}`, "new-proj")).toBe(
        `/dashboard/projects/new-proj/${section}`,
      );
    }
  });

  it("should fallback to overview section when current path is not a section root", () => {
    const miscellaneousPaths = [
      "/dashboard/projects/old/edit",
      "/dashboard/projects/new",
      "/dashboard/projects/old/monitoring/report/run-id",
      "/dashboard/deployments/new",
      "/dashboard/training/jobs/job-id/config",
      "/dashboard/settings/profile",
      "/dashboard/api-keys",
      "/dashboard/notifications",
    ];

    for (const path of miscellaneousPaths) {
      expect(projectSelectionPath(path, "new-proj")).toBe(
        "/dashboard/projects/new-proj/overview",
      );
    }
  });
});

