import { beforeEach, describe, expect, it, vi } from "vitest";
import { apiClient } from "@/shared/api/client";
import { createTrainingJob } from "./trainingApi";

describe("training GPU payload", () => {
  beforeEach(() => vi.restoreAllMocks());

  it.each(["t4", "a10g"] as const)("sends %s model and one GPU", async (model) => {
    const post = vi.spyOn(apiClient, "post")
      .mockResolvedValueOnce({ data: { id: "job-id" } })
      .mockResolvedValueOnce({ data: { id: "job-id", accelerator_model: model } });
    const result = await createTrainingJob({
      name: "training", model_flavor: "pytorch", entry_point: "train.py", requirements_text: "",
      vcpu: 4, memory: 8192, max_runtime_seconds: 3600, accelerator_type: "gpu",
      accelerator_count: 1, accelerator_model: model, source_zip: null, training_data: null,
      project_id: "project-id",
    });
    const form = post.mock.calls[0][1] as FormData;
    expect(form.get("accelerator_type")).toBe("gpu");
    expect(form.get("accelerator_count")).toBe("1");
    expect(form.get("accelerator_model")).toBe(model);
    expect(result.accelerator_model).toBe(model);
    expect(post).toHaveBeenCalledTimes(2);
  });
});
