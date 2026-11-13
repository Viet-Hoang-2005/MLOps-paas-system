import { beforeEach, describe, expect, it, vi } from "vitest";
import { apiClient } from "@/shared/api/client";
import { controlPlaneURL } from "@/shared/api/config";
import { getTrainingRuntimeCapabilities } from "./trainingApi";
import { updateTrainingWorkspace } from "./jobWorkspaceApi";

describe("training GPU payload", () => {
  beforeEach(() => vi.restoreAllMocks());

  it.each(["t4", "a10g"] as const)(
    "persists %s model and one GPU on the draft",
    async (model) => {
      const patch = vi.spyOn(apiClient, "patch").mockResolvedValue({
        data: { id: "job-id", accelerator_model: model },
      });
      const result = await updateTrainingWorkspace("job-id", 4, {
        accelerator_type: "gpu",
        accelerator_count: 1,
        accelerator_model: model,
        local_gpu_id: "",
      });
      expect(patch).toHaveBeenCalledWith(
        controlPlaneURL("/training-workspaces/job-id/"),
        {
          revision: 4,
          accelerator_type: "gpu",
          accelerator_count: 1,
          accelerator_model: model,
          local_gpu_id: "",
        },
      );
      expect(result.accelerator_model).toBe(model);
    },
  );

  it("persists the selected local GPU UUID", async () => {
    const patch = vi
      .spyOn(apiClient, "patch")
      .mockResolvedValue({ data: { id: "job-id" } });
    const uuid = "GPU-12345678-1234-1234-1234-123456789abc";
    await updateTrainingWorkspace("job-id", 7, {
      accelerator_type: "gpu",
      accelerator_count: 1,
      accelerator_model: "",
      local_gpu_id: uuid,
    });
    expect(patch.mock.calls[0][1]).toMatchObject({
      revision: 7,
      local_gpu_id: uuid,
    });
  });

  it("requests a fresh GPU inventory when explicitly refreshed", async () => {
    const get = vi.spyOn(apiClient, "get").mockResolvedValue({ data: {} });
    await getTrainingRuntimeCapabilities(true);
    expect(get).toHaveBeenCalledWith(
      controlPlaneURL("/training-jobs/runtime-capabilities/"),
      { params: { refresh: "1" } },
    );
  });
});
