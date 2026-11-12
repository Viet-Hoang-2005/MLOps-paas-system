import { screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { renderWithProviders } from "test/renderWithProviders";
import { WorkspaceEditor } from "./WorkspaceEditor";
import type { JobWorkspace } from "@/features/training/api/jobWorkspaceApi";
import type { TrainingOutput } from "@/features/training/types";

const mocks = vi.hoisted(() => ({ download: vi.fn(), save: vi.fn() }));
vi.mock("./FileViewer", () => ({ FileViewer: () => null }));
vi.mock("@/features/training/api/jobWorkspaceApi", async (original) => ({
  ...(await original<
    typeof import("@/features/training/api/jobWorkspaceApi")
  >()),
  downloadWorkspaceSelection: mocks.download,
}));
vi.mock("@/features/training/lib/downloadSelection", async (original) => ({
  ...(await original<
    typeof import("@/features/training/lib/downloadSelection")
  >()),
  saveDownload: mocks.save,
}));
const workspace = {
  id: "job-id",
  revision: 1,
  entries: [],
  outputs_purged_at: null,
} as unknown as JobWorkspace;
const outputs: TrainingOutput[] = [
  {
    id: "model-id",
    relative_path: "Model/chosen.joblib",
    kind: "model",
    s3_uri: "s3://test-bucket/chosen",
    checksum: "checksum",
    content_type: "application/octet-stream",
    created_at: "2026-11-12T00:00:00Z",
    size_bytes: 12,
    metadata: { group: "model" },
  },
];

beforeEach(() => {
  vi.clearAllMocks();
  mocks.download.mockResolvedValue({
    blob: new Blob(["test"]),
    filename: "download",
  });
});

function show(files: TrainingOutput[], language: "en" | "vi" = "en") {
  return renderWithProviders(
    <WorkspaceEditor
      workspace={workspace}
      entries={[]}
      outputs={files}
      runId="job-id"
      entryPoint="train.py"
      readOnly
      onRefresh={vi.fn()}
      onDirty={vi.fn()}
      onBusy={vi.fn()}
    />,
    { language },
  );
}

describe("public Output tree", () => {
  it.each(["en", "vi"] as const)(
    "keeps two empty roots and disables Download in %s",
    async (language) => {
      const { user, i18n } = show([], language);
      await user.click(
        screen.getByRole("button", { name: i18n.t("training:studio.output") }),
      );
      expect(screen.getByRole("button", { name: "Model" })).toBeInTheDocument();
      expect(
        screen.getByRole("button", { name: "Metadata" }),
      ).toBeInTheDocument();
      expect(
        screen.getByRole("button", {
          name: i18n.t("training:studio.download"),
        }),
      ).toBeDisabled();
      expect(screen.queryByText("model.tar.gz")).not.toBeInTheDocument();
      expect(screen.queryByText("_mlops")).not.toBeInTheDocument();
    },
  );

  it("downloads all public Output, then selected directory and exact file", async () => {
    const { user } = show(outputs);
    await user.click(screen.getByRole("button", { name: "Output" }));
    await user.click(screen.getByRole("button", { name: "Download" }));
    await waitFor(() =>
      expect(mocks.download).toHaveBeenLastCalledWith(
        "job-id",
        "outputs",
        null,
      ),
    );
    await user.click(screen.getByRole("button", { name: "Model" }));
    await user.click(screen.getByRole("button", { name: "Download" }));
    await waitFor(() =>
      expect(mocks.download).toHaveBeenLastCalledWith(
        "job-id",
        "outputs",
        "Model",
      ),
    );
    await user.click(screen.getByText("chosen.joblib"));
    await user.click(screen.getAllByRole("button", { name: "Download" })[0]);
    await waitFor(() =>
      expect(mocks.download).toHaveBeenLastCalledWith(
        "job-id",
        "outputs",
        "Model/chosen.joblib",
      ),
    );
    await user.click(screen.getByRole("button", { name: "Metadata" }));
    expect(screen.getByRole("button", { name: "Download" })).toBeDisabled();
  });
});
