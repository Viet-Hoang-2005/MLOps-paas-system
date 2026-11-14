import { screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { Route, Routes } from "react-router-dom";
import { renderWithProviders } from "test/renderWithProviders";
import TrainingWorkspacePage from "./TrainingWorkspacePage";

vi.mock("react-router-dom", async (original) => ({
  ...(await original<typeof import("react-router-dom")>()),
  useBlocker: () => ({ state: "unblocked" }),
}));
vi.mock("@/shared/hooks/useRuntimeLogStream", () => ({
  useRuntimeLogStream: () => ({
    logs: [],
    status: null,
    error: "",
    isPolling: false,
    refresh: vi.fn(),
  }),
}));
vi.mock("@/features/training/components/WorkspaceEditor", () => ({
  WorkspaceEditorLoading: () => <div>Loading editor</div>,
  WorkspaceEditor: ({
    loading,
    readOnly,
  }: {
    loading: boolean;
    readOnly: boolean;
  }) => (
    <div data-testid="editor" data-loading={loading} data-readonly={readOnly} />
  ),
}));
vi.mock("@/features/training/api/jobWorkspaceApi", async (original) => ({
  ...(await original<
    typeof import("@/features/training/api/jobWorkspaceApi")
  >()),
  getTrainingWorkspace: () =>
    Promise.resolve({
      id: "workspace",
      status: "preparing",
      revision: 1,
      entries: [],
      environment: {},
      secrets: [],
      job_count: 1,
      active_job_id: "job",
      entry_point: "train.py",
      model_flavor: "sklearn",
      vcpu: 1,
      memory_mb: 2048,
      accelerator_type: "none",
      accelerator_count: 0,
      max_runtime_seconds: 900,
    }),
  getWorkspaceJob: () =>
    Promise.resolve({
      id: "job",
      workspace_id: "workspace",
      status: "pending",
      submitted_at: null,
      entry_point: "train.py",
      model_flavor: "sklearn",
      vcpu: 1,
      memory_mb: 2048,
      accelerator_type: "none",
      accelerator_count: 0,
      max_runtime_seconds: 900,
      environment: {},
      secrets: [],
      outputs: [],
      output_available: false,
    }),
}));
vi.mock("@/features/training/api/trainingApi", async (original) => ({
  ...(await original<typeof import("@/features/training/api/trainingApi")>()),
  getTrainingUsage: () => Promise.resolve(null),
  getTrainingRuntimeCapabilities: () =>
    Promise.resolve({
      backend: "argo",
      enabled: true,
      runtime_options_seconds: [900],
      cpu_profiles: [{ id: "small", vcpu: 1, memory_mb: 2048 }],
      accelerators: [{ type: "none", counts: [0] }],
    }),
}));

describe("Input preparation UI", () => {
  it.each(["en", "vi"] as const)(
    "shows Preparing rather than an idle terminal in %s",
    async (language) => {
      const { i18n } = renderWithProviders(
        <Routes>
          <Route
            path="/workspaces/:workspaceId/job/:jobId"
            element={<TrainingWorkspacePage />}
          />
        </Routes>,
        { language, initialEntries: ["/workspaces/workspace/job/job"] },
      );
      expect(
        (await screen.findAllByText(i18n.t("training:studio.preparingInput")))
          .length,
      ).toBeGreaterThan(0);
      expect(screen.getByTestId("editor")).toHaveAttribute(
        "data-loading",
        "true",
      );
      expect(screen.getByTestId("editor")).toHaveAttribute(
        "data-readonly",
        "true",
      );
      expect(
        screen.queryByText(i18n.t("training:studio.logPlaceholder")),
      ).not.toBeInTheDocument();
      expect(
        screen.getByRole("button", { name: i18n.t("training:studio.next") }),
      ).toBeDisabled();
    },
  );
});
