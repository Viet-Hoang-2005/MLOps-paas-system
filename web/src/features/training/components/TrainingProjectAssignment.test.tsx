import { screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { renderWithProviders } from "test/renderWithProviders";
import { TrainingProjectAssignment } from "./TrainingProjectAssignment";
import type { TrainingJob } from "@/features/training/types";

const mocks = vi.hoisted(() => ({
  output: vi.fn(),
  assign: vi.fn(),
  projects: vi.fn(),
  patch: vi.fn(),
}));
vi.mock("@/features/training/api/trainingApi", () => ({
  getModelOutputSummary: mocks.output,
  patchModelOutput: mocks.patch,
}));
vi.mock("@/features/training/api/jobWorkspaceApi", () => ({
  assignTrainingProject: mocks.assign,
}));
vi.mock("@/shared/api/catalogApi", () => ({
  listModelProjects: mocks.projects,
}));

const job = {
  id: "job-id",
  project_id: "project-id",
  status: "completed",
  requirements_text: "",
} as TrainingJob;
const output = {
  output_revision: 1,
  can_edit: true,
  selection: {},
  available_outputs: [
    {
      id: "model-id",
      relative_path: "Model/chosen.joblib",
      size_bytes: 12,
      metadata: { group: "model" },
    },
    {
      id: "json-id",
      relative_path: "Metadata/arbitrary.json",
      size_bytes: 12,
      metadata: { group: "metadata" },
    },
    {
      id: "large-id",
      relative_path: "Metadata/large.json",
      size_bytes: 2 * 1024 * 1024,
      metadata: { group: "metadata" },
    },
  ],
};

beforeEach(() => {
  vi.clearAllMocks();
  mocks.output.mockResolvedValue(output);
  mocks.projects.mockResolvedValue({
    models: [{ id: "project-id", name: "Existing", is_active: true }],
  });
  mocks.assign.mockResolvedValue(job);
});

describe("explicit training artifact assignment", () => {
  it.each(["en", "vi"] as const)(
    "requires manual selection even for one model in %s",
    async (language) => {
      const { user, i18n } = renderWithProviders(
        <TrainingProjectAssignment
          job={job}
          onBack={vi.fn()}
          onSaved={vi.fn()}
        />,
        { language },
      );
      const save = screen.getByRole("button", {
        name: i18n.t("training:studio.save"),
      });
      await waitFor(() => expect(mocks.output).toHaveBeenCalled());
      expect(save).toBeDisabled();
      expect(
        screen.getAllByText(i18n.t("training:studio.artifactSelection.none")),
      ).toHaveLength(6);
      await user.click(
        screen.getByRole("combobox", {
          name: i18n.t("training:studio.artifactSelection.model"),
        }),
      );
      const option = await screen.findByRole("option", {
        name: /Model\/chosen.joblib/,
      });
      option.focus();
      await user.keyboard("{Enter}");
      expect(save).toBeEnabled();
      await user.click(save);
      await waitFor(() =>
        expect(mocks.assign).toHaveBeenCalledWith(
          "job-id",
          1,
          { project_id: "project-id" },
          { modelId: "model-id", artifacts: {}, files: {} },
        ),
      );
      expect(mocks.patch).not.toHaveBeenCalled();
    },
  );

  it("selects arbitrary Metadata JSON and clears it when changing source", async () => {
    const { user } = renderWithProviders(
      <TrainingProjectAssignment
        job={job}
        onBack={vi.fn()}
        onSaved={vi.fn()}
      />,
    );
    await user.click(
      await screen.findByRole("combobox", { name: "Raw Model Artifact" }),
    );
    await user.click(
      await screen.findByRole("option", { name: /Model\/chosen.joblib/ }),
    );
    await user.click(screen.getByRole("combobox", { name: "Metrics" }));
    await user.click(
      await screen.findByRole("option", { name: "Select from Metadata" }),
    );
    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
    await user.click(
      screen.getByRole("combobox", { name: "Metrics: Select a JSON file" }),
    );
    expect(
      screen.queryByRole("option", { name: /large.json/ }),
    ).not.toBeInTheDocument();
    await user.click(
      await screen.findByRole("option", { name: "Metadata/arbitrary.json" }),
    );
    await user.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() =>
      expect(mocks.assign).toHaveBeenCalledWith(
        "job-id",
        1,
        { project_id: "project-id" },
        expect.objectContaining({ artifacts: { metrics: "json-id" } }),
      ),
    );
    await user.click(screen.getByRole("combobox", { name: "Metrics" }));
    await user.click(await screen.findByRole("option", { name: "Not used" }));
    await user.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() =>
      expect(mocks.assign).toHaveBeenLastCalledWith(
        "job-id",
        1,
        { project_id: "project-id" },
        expect.objectContaining({ artifacts: {} }),
      ),
    );
  });

  it("reloads saved selections and blocks saving after revision conflict", async () => {
    mocks.output.mockResolvedValue({
      ...output,
      selection: { model_id: "model-id", artifacts: { metrics: "json-id" } },
    });
    mocks.assign.mockRejectedValue({
      isAxiosError: true,
      response: { status: 409, data: { detail: "Revision conflict" } },
    });
    const { user } = renderWithProviders(
      <TrainingProjectAssignment
        job={job}
        onBack={vi.fn()}
        onSaved={vi.fn()}
      />,
    );
    const save = screen.getByRole("button", { name: "Save" });
    await waitFor(() => expect(save).toBeEnabled());
    expect(screen.getByText("Metadata/arbitrary.json")).toBeInTheDocument();
    await user.click(save);
    await waitFor(() => expect(save).toBeDisabled());
    mocks.output.mockResolvedValue({
      ...output,
      output_revision: 2,
      selection: { model_id: "model-id", artifacts: {} },
    });
    await user.click(
      await screen.findByRole("button", { name: "Reload / retry" }),
    );
    await waitFor(() => expect(save).toBeEnabled());
    expect(screen.getAllByText("Not used")).toHaveLength(6);
  });

  it("uploads a JSON through FileDropzone and discards it when changing source", async () => {
    const { user, container } = renderWithProviders(
      <TrainingProjectAssignment
        job={job}
        onBack={vi.fn()}
        onSaved={vi.fn()}
      />,
    );
    await user.click(
      await screen.findByRole("combobox", { name: "Raw Model Artifact" }),
    );
    await user.click(
      await screen.findByRole("option", { name: /chosen.joblib/ }),
    );
    await user.click(screen.getByRole("combobox", { name: "Metrics" }));
    await user.click(
      await screen.findByRole("option", { name: "Upload new JSON" }),
    );
    const file = new File(['{"accuracy":0.8}'], "scores.json", {
      type: "application/json",
    });
    await user.upload(
      container.querySelector<HTMLInputElement>('input[accept=".json"]')!,
      file,
    );
    await user.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() =>
      expect(mocks.assign).toHaveBeenCalledWith(
        "job-id",
        1,
        { project_id: "project-id" },
        expect.objectContaining({ files: { metrics: file }, artifacts: {} }),
      ),
    );
    await user.click(screen.getByRole("combobox", { name: "Metrics" }));
    await user.click(
      await screen.findByRole("option", { name: "Select from Metadata" }),
    );
    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
    expect(container.querySelector('input[accept=".json"]')).toBeNull();
  });
});
