import { describe, expect, it } from "vitest";
import { projectPaths } from "./paths";

describe("project workflow routes", () => {
  const projectId = "project-uuid";

  it("keeps workflow routes scoped to the project in the URL", () => {
    expect(projectPaths.overviewPresent(projectId)).toBe(
      `/dashboard/projects/${projectId}/overview/present`,
    );
    expect(projectPaths.overviewDraft(projectId)).toBe(
      `/dashboard/projects/${projectId}/overview/draft`,
    );
    expect(projectPaths.evolutionVersion(projectId, "version-uuid")).toBe(
      `/dashboard/projects/${projectId}/evolution/versions/version-uuid`,
    );
    expect(projectPaths.trainingJob(projectId, "job-uuid")).toBe(
      `/dashboard/projects/${projectId}/training/jobs/job-uuid`,
    );
  });
});
