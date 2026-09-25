import { beforeEach, describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  patch: vi.fn(),
  delete: vi.fn(),
}));

vi.mock("@/shared/api/client", () => ({ apiClient: api }));
vi.mock("@/shared/api/config", () => ({ controlPlaneURL: (path: string) => path }));

import { patchDraft, saveDraft } from "./draftApi";

describe("Draft API contract", () => {
  beforeEach(() => vi.clearAllMocks());

  it("uses optimistic concurrency when updating metadata", async () => {
    api.patch.mockResolvedValue({ data: { revision: 5 } });

    await patchDraft("project-uuid", 4, {
      flavor: "pytorch",
      artifact_format: "raw",
      requirements_snapshot: "torch==2.0",
    });

    expect(api.patch).toHaveBeenCalledWith("/models/project-uuid/draft/", {
      expected_revision: 4,
      flavor: "pytorch",
      artifact_format: "raw",
      requirements_snapshot: "torch==2.0",
    });
  });

  it("saves a Draft revision using the expected revision", async () => {
    api.post.mockResolvedValue({ data: { saved_revision: 7 } });

    await saveDraft("project-uuid", 7);

    expect(api.post).toHaveBeenCalledWith(
      "/models/project-uuid/draft/save/",
      { expected_revision: 7 },
    );
  });
});
