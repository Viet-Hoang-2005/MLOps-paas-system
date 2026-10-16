import {
  deploymentMatchesBuild,
  isDeployableBuild,
  isRegisteredBuild,
  projectDeploymentBlocked,
} from "@/features/deployments/deploymentEligibility";
import type { Build, Deployment } from "@/features/projects/types";
import { describe, expect, it } from "vitest";

describe("Deployment Eligibility & Build Matching", () => {
  const registeredBuild = {
    id: "build-a",
    project_id: "project-a",
    version_id: "version-a",
    status: "ready",
    deletion_state: "active",
    registration_status: "registered",
    image_uri: "registry.example.com/churn:v1",
    created_at: "2026-01-01T00:00:00Z",
  } as unknown as Build;

  it("should validate deployable builds matching active project", () => {
    expect(isRegisteredBuild(registeredBuild)).toBe(true);
    expect(
      isRegisteredBuild({
        ...registeredBuild,
        registration_status: "unregistered",
      }),
    ).toBe(false);
    expect(isDeployableBuild(registeredBuild, "project-a")).toBe(true);
    expect(isDeployableBuild(registeredBuild, "project-b")).toBe(false);
    expect(
      isDeployableBuild(
        { ...registeredBuild, registration_status: "unregistered" },
        "project-a",
      ),
    ).toBe(false);
    expect(
      isDeployableBuild({ ...registeredBuild, version_id: null }, "project-a"),
    ).toBe(false);
    expect(
      isDeployableBuild({ ...registeredBuild, status: "building" }, "project-a"),
    ).toBe(false);
    expect(
      isDeployableBuild(
        { ...registeredBuild, deletion_state: "deleting" },
        "project-a",
      ),
    ).toBe(false);
  });

  it("should match deployment only if build_id and version_id match", () => {
    const deployment = {
      id: "deploy-1",
      build_id: "build-a",
      version_id: "version-a",
      status: "succeeded",
    } as unknown as Deployment;

    expect(deploymentMatchesBuild(deployment, registeredBuild)).toBe(true);
    expect(
      deploymentMatchesBuild({ ...deployment, build_id: "build-b" }, registeredBuild),
    ).toBe(false);
    expect(
      deploymentMatchesBuild({ ...deployment, version_id: "version-b" }, registeredBuild),
    ).toBe(false);
  });

  it("should detect blocked project deployments when in-progress", () => {
    const activeDeployments = [
      {
        id: "deploy-1",
        build_id: "build-a",
        version_id: "version-a",
        status: "deploying",
      },
    ] as unknown as Deployment[];

    expect(
      projectDeploymentBlocked(activeDeployments, [registeredBuild]),
    ).toBe(true);

    expect(
      projectDeploymentBlocked(
        [{ ...activeDeployments[0], status: "succeeded" }],
        [registeredBuild],
      ),
    ).toBe(false);
  });
});
