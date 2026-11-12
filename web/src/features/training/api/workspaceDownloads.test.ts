import { beforeEach, describe, expect, it, vi } from "vitest";
import { apiClient } from "@/shared/api/client";
import { controlPlaneURL } from "@/shared/api/config";
import { downloadWorkspaceSelection } from "./jobWorkspaceApi";

describe("workspace download API", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("downloads the exact selected Input path and keeps its filename", async () => {
    const blob = new Blob([new Uint8Array([0, 255, 128])]);
    const get = vi
      .spyOn(apiClient, "get")
      .mockResolvedValue({
        data: blob,
        headers: {
          "content-disposition":
            "attachment; filename*=utf-8''hu%E1%BA%A5n.zip",
          "content-type": "application/zip",
        },
      });
    const result = await downloadWorkspaceSelection(
      "job",
      "input",
      "data/huấn",
      4,
    );
    expect(get).toHaveBeenCalledWith(
      controlPlaneURL("/training-jobs/job/input/download/"),
      {
        params: { path: "data/huấn", revision: 4 },
        responseType: "blob",
        timeout: 120000,
      },
    );
    expect(result.blob).toBe(blob);
    expect(result.filename).toBe("huấn.zip");
  });

  it("omits path when downloading all Output", async () => {
    const get = vi
      .spyOn(apiClient, "get")
      .mockResolvedValue({
        data: new Blob(),
        headers: {
          "content-disposition": 'attachment; filename="output.zip"',
          "content-type": "application/zip",
        },
      });
    const result = await downloadWorkspaceSelection("job", "outputs");
    expect(get).toHaveBeenCalledWith(
      controlPlaneURL("/training-jobs/job/outputs/download/"),
      expect.objectContaining({ params: {} }),
    );
    expect(result.filename).toBe("output.zip");
  });
});
