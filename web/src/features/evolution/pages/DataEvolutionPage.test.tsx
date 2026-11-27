import * as evolutionApi from "@/features/evolution/api/evolutionApi";
import type { ModelVersion } from "@/features/projects/types";
import * as filesApi from "@/shared/api/files";
import { screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { renderWithProviders } from "test/renderWithProviders";
import { DataEvolutionPage } from "./DataEvolutionPage";

const version: ModelVersion = {
  id: "version",
  project_id: "project",
  version: "1",
  source_job_id: null,
  requirements_snapshot: "",
  flavor: "sklearn",
  stage: "none",
  deployability: "deployable",
  deployability_reason: "",
  metrics_summary: {},
  params_summary: {},
  insights_summary: {},
  artifacts: [{
    id: "artifact",
    kind: "reference_data",
    name: "reference.csv",
    uri: "s3://bucket/reference.csv",
    checksum: "",
    size_bytes: 123,
    content_type: "text/csv",
    metadata: {},
    created_at: "",
  }],
  metrics: [],
  events: [],
  registered_at: "",
};

afterEach(() => vi.restoreAllMocks());

it.each(["sample", "error"])("downloads the original CSV with a preview %s", async (preview) => {
  const readPreview = vi.spyOn(evolutionApi, "getVersionReferencePreview");
  if (preview === "sample") {
    readPreview.mockResolvedValue({
      filename: "reference.csv", format: "csv", columns: ["name"], rows: [["first"]], total_rows: 1000,
    });
  } else {
    readPreview.mockRejectedValue(new Error("Preview unavailable"));
  }
  const download = vi.spyOn(filesApi, "downloadOriginal").mockResolvedValue(undefined);
  const { user } = renderWithProviders(<DataEvolutionPage projectId="project" version={version} />);
  if (preview === "sample") {
    await screen.findByDisplayValue("first");
  } else {
    await screen.findByText("No CSV data");
  }
  await user.click(screen.getByRole("button", { name: "Download original CSV" }));
  await waitFor(() => expect(download).toHaveBeenCalledExactlyOnceWith(
    "/registry/versions/version/reference-download/", undefined,
  ));
});
