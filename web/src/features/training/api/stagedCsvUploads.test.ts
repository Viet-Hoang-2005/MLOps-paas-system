import { addSupplementalArtifacts } from "@/features/evolution/api/evolutionApi";
import { createDriftMonitoringJob } from "@/features/monitoring/api/driftApi";
import { apiClient } from "@/shared/api/client";
import * as s3Upload from "@/shared/api/s3Upload";
import { afterEach, expect, it, vi } from "vitest";
import { saveWorkspaceEntry } from "./jobWorkspaceApi";
import { patchModelOutput } from "./trainingApi";

afterEach(() => vi.restoreAllMocks());

it("sends upload tokens instead of CSV bodies in all four commit requests", async () => {
  const file = new File(["column\nrow\n"], "data.csv", { type: "text/csv" });
  const stage = vi.spyOn(s3Upload, "stageCsvUpload").mockImplementation((purpose) =>
    Promise.resolve(`token-${purpose}`),
  );
  const request = vi.spyOn(apiClient, "request").mockResolvedValue({ data: {} });
  const patch = vi.spyOn(apiClient, "patch").mockResolvedValue({ data: {} });
  const post = vi.spyOn(apiClient, "post").mockResolvedValue({ data: {} });
  const script = new File(["print(1)"], "train.py", { type: "text/plain" });

  await saveWorkspaceEntry("workspace-id", 2, { path: "data.csv", kind: "data", file });
  await patchModelOutput("job-id", { output_revision: 3, reference_data_file: file, source_code_file: script });
  await addSupplementalArtifacts("version-id", { reference_data_file: file });
  await createDriftMonitoringJob({
    project_id: "project-id",
    version_id: "version-id",
    trigger_threshold: 100,
    reference_file: file,
  });

  expect(stage.mock.calls).toEqual([
    ["workspace", "workspace-id", file, 2],
    ["training-output", "job-id", file, 3],
    ["version", "version-id", file],
    ["drift-monitor", "version-id", file],
  ]);
  const workspaceForm = request.mock.calls[0][0].data as FormData;
  const outputForm = patch.mock.calls[0][1] as FormData;
  const versionForm = post.mock.calls[0][1] as FormData;
  const monitorForm = post.mock.calls[1][1] as FormData;
  expect(workspaceForm.get("csv_upload_token")).toBe("token-workspace");
  expect(workspaceForm.has("file")).toBe(false);
  expect(outputForm.get("csv_upload_token")).toBe("token-training-output");
  expect(outputForm.get("source_code_file")).toBe(script);
  expect(outputForm.has("reference_data_file")).toBe(false);
  expect(versionForm.get("csv_upload_token")).toBe("token-version");
  expect(versionForm.has("reference_data_file")).toBe(false);
  expect(monitorForm.get("csv_upload_token")).toBe("token-drift-monitor");
  expect(monitorForm.has("reference_file")).toBe(false);
});
