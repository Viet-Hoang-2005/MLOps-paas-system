import { screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Route, Routes } from "react-router-dom";
import { renderWithProviders } from "test/renderWithProviders";
import TrainingWorkspacePage from "./TrainingWorkspacePage";

const mockGetTrainingWorkspace = vi.fn();
const mockGetWorkspaceJob = vi.fn();
const mockGetRunInput = vi.fn();

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
    inputSource,
    entries,
  }: {
    loading: boolean;
    readOnly: boolean;
    inputSource?: "workspace" | "snapshot";
    entries?: unknown[];
  }) => (
    <div
      data-testid="editor"
      data-loading={loading}
      data-readonly={readOnly}
      data-input-source={inputSource}
      data-entry-count={entries?.length ?? 0}
    />
  ),
}));
vi.mock("@/features/training/api/jobWorkspaceApi", async (original) => ({
  ...(await original<
    typeof import("@/features/training/api/jobWorkspaceApi")
  >()),
  getTrainingWorkspace: (...args: unknown[]) => mockGetTrainingWorkspace(...args),
  getWorkspaceJob: (...args: unknown[]) => mockGetWorkspaceJob(...args),
  getRunInput: (...args: unknown[]) => mockGetRunInput(...args),
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
  beforeEach(() => {
    vi.clearAllMocks();
    mockGetTrainingWorkspace.mockResolvedValue({
      id: "workspace",
      status: "preparing",
      revision: 1,
      entries: [
        { id: "e1", path: "train.py", kind: "script", size_bytes: 10 },
      ],
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
    });
    mockGetWorkspaceJob.mockResolvedValue({
      id: "job",
      workspace_id: "workspace",
      status: "pending",
      submitted_at: null,
      input_revision: 1,
      entries: [],
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
    });
    mockGetRunInput.mockResolvedValue({
      entries: [],
      entry_point: "train.py",
    });
  });

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
        "false",
      );
      expect(screen.getByTestId("editor")).toHaveAttribute(
        "data-readonly",
        "true",
      );
      expect(screen.getByTestId("editor")).toHaveAttribute(
        "data-input-source",
        "workspace",
      );
      expect(screen.getByTestId("editor")).toHaveAttribute(
        "data-entry-count",
        "1",
      );
      expect(mockGetRunInput).not.toHaveBeenCalled();
      expect(
        screen.queryByText(i18n.t("training:studio.logPlaceholder")),
      ).not.toBeInTheDocument();
      expect(
        screen.getByRole("button", { name: i18n.t("training:studio.next") }),
      ).toBeDisabled();
    },
  );

  it("keeps workspace input read-only for submitted jobs matching workspace revision", async () => {
    mockGetTrainingWorkspace.mockResolvedValue({
      id: "workspace",
      status: "running",
      revision: 3,
      entries: [
        { id: "e1", path: "train.py", kind: "script", size_bytes: 10 },
      ],
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
    });
    mockGetWorkspaceJob.mockResolvedValue({
      id: "job",
      workspace_id: "workspace",
      status: "running",
      submitted_at: "2026-11-25T00:00:00Z",
      input_revision: 3,
      entries: [],
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
    });

    renderWithProviders(
      <Routes>
        <Route
          path="/workspaces/:workspaceId/job/:jobId"
          element={<TrainingWorkspacePage />}
        />
      </Routes>,
      { language: "en", initialEntries: ["/workspaces/workspace/job/job"] },
    );

    const editor = await screen.findByTestId("editor");
    expect(editor).toHaveAttribute("data-loading", "false");
    expect(editor).toHaveAttribute("data-readonly", "true");
    expect(editor).toHaveAttribute("data-input-source", "workspace");
    expect(editor).toHaveAttribute("data-entry-count", "1");
    expect(mockGetRunInput).not.toHaveBeenCalled();
  });

  it("loads job snapshot input when viewing a job from a different workspace revision", async () => {
    mockGetTrainingWorkspace.mockResolvedValue({
      id: "workspace",
      status: "ready",
      revision: 4,
      entries: [],
      environment: {},
      secrets: [],
      job_count: 1,
      active_job_id: null,
      entry_point: "train.py",
      model_flavor: "sklearn",
      vcpu: 1,
      memory_mb: 2048,
      accelerator_type: "none",
      accelerator_count: 0,
      max_runtime_seconds: 900,
    });
    mockGetWorkspaceJob.mockResolvedValue({
      id: "job",
      workspace_id: "workspace",
      status: "completed",
      submitted_at: "2026-11-25T00:00:00Z",
      input_revision: 2,
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
      output_available: true,
    });

    renderWithProviders(
      <Routes>
        <Route
          path="/workspaces/:workspaceId/job/:jobId"
          element={<TrainingWorkspacePage />}
        />
      </Routes>,
      { language: "en", initialEntries: ["/workspaces/workspace/job/job"] },
    );

    const editor = await screen.findByTestId("editor");
    expect(editor).toHaveAttribute("data-readonly", "true");
    expect(editor).toHaveAttribute("data-input-source", "snapshot");
    expect(mockGetRunInput).toHaveBeenCalledWith("job");
  });
});
