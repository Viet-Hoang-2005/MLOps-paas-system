import { beforeEach, describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({ post: vi.fn() }));

vi.mock("@/shared/api/client", () => ({ apiClient: api }));
vi.mock("@/shared/api/config", () => ({ controlPlaneURL: (path: string) => path }));

import { deployBuild } from "./deployApi";

describe("deployment API contract", () => {
  beforeEach(() => vi.clearAllMocks());

  it("deploys an immutable version to an explicit target", async () => {
    api.post.mockResolvedValue({ data: { id: "deployment-uuid" } });

    await deployBuild("version-uuid", "production");

    expect(api.post).toHaveBeenCalledWith("/deployments/", {
      version: "version-uuid",
      target: "production",
    });
  });
});
