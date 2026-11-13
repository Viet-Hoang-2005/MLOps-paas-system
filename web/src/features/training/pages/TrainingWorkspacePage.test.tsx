import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Route, Routes } from "react-router-dom";
import { renderWithProviders } from "test/renderWithProviders";
import TrainingWorkspacePage from "./TrainingWorkspacePage";
import type {
  TrainingJob,
  TrainingRuntimeCapabilities,
} from "@/features/training/types";

const mocks = vi.hoisted(() => ({
  get: vi.fn(),
  getRun: vi.fn(),
  update: vi.fn(),
  run: vi.fn(),
  input: vi.fn(),
  save: vi.fn(),
  caps: vi.fn(),
  metrics: vi.fn(),
}));
vi.mock("react-router-dom", async (original) => ({
  ...(await original<typeof import("react-router-dom")>()),
  useBlocker: () => ({ state: "unblocked" }),
}));
vi.mock("@/features/training/api/jobWorkspaceApi", async (original) => ({
  ...(await original<
    typeof import("@/features/training/api/jobWorkspaceApi")
  >()),
  getTrainingWorkspace: mocks.get,
  getWorkspaceJob: mocks.getRun,
  runTrainingWorkspace: mocks.run,
  updateTrainingWorkspace: mocks.update,
  getRunInput: mocks.input,
}));
vi.mock("@/features/training/api/trainingApi", async (original) => ({
  ...(await original<typeof import("@/features/training/api/trainingApi")>()),
  getTrainingRuntimeCapabilities: mocks.caps,
  getTrainingJobMetrics: mocks.metrics,
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
vi.mock("@/features/training/components/WorkspaceEditor", async () => {
  const { forwardRef, useImperativeHandle } = await import("react");
  return {
    WorkspaceEditor: forwardRef(function MockEditor(
      { readOnly }: { readOnly: boolean },
      ref,
    ) {
      useImperativeHandle(ref, () => ({ saveAll: mocks.save }));
      return <div data-testid="workspace-editor" data-readonly={readOnly} />;
    }),
  };
});
const job = {
  id: "run-one",
  project_id: null,
  submitted_at: "2026-11-11T00:00:00Z",
  status: "running",
  model_flavor: "sklearn",
  entry_point: "train.py",
  requirements_text: "",
  vcpu: 1,
  memory_mb: 2048,
  max_runtime_seconds: 900,
  accelerator_type: "none",
  outputs: [],
  output_available: false,
  output_revision: 1,
} as unknown as TrainingJob;
const workspace = {
  ...job,
  status: "ready",
  job_count: 0,
  active_job_id: null,
  submitted_at: null,
  id: "workspace",
  revision: 1,
  entry_point: "train.py",
  entries: [],
  environment: {},
  secrets: [],
  secrets_available: true,
};
const caps: TrainingRuntimeCapabilities = {
  enabled: true,
  backend: "argo",
  runtime_options_seconds: [900, 86400],
  cpu_profiles: [{ id: "small", vcpu: 1, memory_mb: 2048 }],
  accelerators: [
    { type: "none", counts: [0] },
    { type: "gpu", model: "t4", counts: [1] },
    { type: "gpu", model: "a10g", counts: [1] },
  ],
};
function show(language: "en" | "vi" = "en", query = "") {
  return renderWithProviders(
    <Routes>
      <Route
        path="/dashboard/training/workspaces/:workspaceId"
        element={<TrainingWorkspacePage />}
      />
      <Route
        path="/dashboard/training/workspaces/:workspaceId/jobs/:jobId"
        element={<TrainingWorkspacePage />}
      />
    </Routes>,
    {
      language,
      initialEntries: [`/dashboard/training/workspaces/workspace${query}`],
    },
  );
}
describe("training workspace flow", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.get.mockResolvedValue(workspace);
    mocks.update.mockResolvedValue(workspace);
    mocks.getRun.mockResolvedValue({ ...job, environment: {}, secrets: [] });
    mocks.caps.mockResolvedValue(caps);
    mocks.metrics.mockResolvedValue({
      job_id: "workspace",
      status: "available",
      backend: "argo",
      poll_interval_seconds: 5,
      latest: null,
    });
    mocks.save.mockResolvedValue(6);
    mocks.run.mockImplementation(() => {
      mocks.get.mockResolvedValue({
        ...workspace,
        status: "running",
        active_job_id: "run-one",
        job_count: 1,
      });
      return Promise.resolve(job);
    });
    mocks.input.mockResolvedValue({ entries: [], entry_point: "train.py" });
  });
  it.each(["en", "vi"] as const)(
    "runs without a project and saves pending editor changes first in %s",
    async (language) => {
      show(language);
      const run = await screen.findByRole("button", {
        name: language === "en" ? "Run" : "Chạy",
      });
      await waitFor(() => expect(run).toBeEnabled());
      await userEvent.click(run);
      await waitFor(() => expect(mocks.run).toHaveBeenCalled());
      expect(mocks.save).toHaveBeenCalled();
      const [id, revision, key, payload] = mocks.run.mock.calls[0];
      expect(id).toBe("workspace");
      expect(revision).toBe(6);
      expect(key).toEqual(expect.any(String));
      expect(payload).toBeUndefined();
      expect(
        screen.queryByLabelText(language === "en" ? "Name" : "Tên"),
      ).not.toBeInTheDocument();

      await waitFor(() =>
        expect(screen.getByTestId("workspace-editor")).toHaveAttribute(
          "data-readonly",
          "true",
        ),
      );
      expect(
        screen.getByRole("button", {
          name: language === "en" ? "Continue" : "Tiếp tục",
        }),
      ).toBeDisabled();
    },
  );
  it("preserves the selected GPU model in the run payload", async () => {
    show();
    await screen.findByRole("button", { name: "Run" });
    await userEvent.click(screen.getByLabelText("GPU"));
    await userEvent.click(await screen.findByRole("option", { name: /a10g/i }));
    await userEvent.click(screen.getByRole("button", { name: "Run" }));
    await waitFor(() => expect(mocks.run).toHaveBeenCalled());
    expect(mocks.run.mock.calls[0][0]).toBe("workspace");
    expect(mocks.update).toHaveBeenCalledWith(
      "workspace",
      6,
      expect.objectContaining({
        accelerator_model: "a10g",
        accelerator_count: 1,
      }),
    );
  });
  it("does not submit when saving configuration fails", async () => {
    mocks.update.mockRejectedValue(new Error("Revision conflict"));
    show();
    const run = await screen.findByRole("button", { name: "Run" });
    await waitFor(() => expect(run).toBeEnabled());
    await userEvent.click(run);
    await waitFor(() => expect(mocks.update).toHaveBeenCalled());
    expect(mocks.run).not.toHaveBeenCalled();
  });
  it("loads the job snapshot and enables assignment only with verified model output", async () => {
    mocks.getRun.mockResolvedValue({
      ...job,
      status: "completed",
      output_available: true,
      environment: {},
      secrets: [],
    });
    show("en", "/jobs/run-one");
    await waitFor(() => expect(mocks.input).toHaveBeenCalledWith("run-one"));
    expect(screen.getByRole("button", { name: "Continue" })).toBeEnabled();
    expect(await screen.findByTestId("workspace-editor")).toHaveAttribute(
      "data-readonly",
      "true",
    );
  });
  it("renders 4 CardSummary metrics cards only when training is running", async () => {
    mocks.metrics.mockResolvedValue({
      job_id: "workspace",
      status: "available",
      backend: "argo",
      poll_interval_seconds: 5,
      latest: {
        timestamp: "2026-11-11T00:00:00Z",
        cpu_percent: 42,
        cpu_limit_cores: 1,
        memory_used_mb: 512,
        memory_limit_mb: 2048,
        memory_percent: 25,
        gpu_percent: null,
        gpu_memory_used_mb: null,
        gpu_memory_total_mb: null,
        gpu_memory_percent: null,
      },
    });
    const { unmount } = show("en");
    expect(screen.queryByText("% CPU")).not.toBeInTheDocument();

    unmount();
    mocks.getRun.mockResolvedValue({
      ...job,
      status: "running",
      started_at: "2026-11-11T00:00:00Z",
      environment: {},
      secrets: [],
    });
    show("en", "/jobs/run-one");
    expect(await screen.findByText("% CPU")).toBeInTheDocument();
    expect(await screen.findByText("42%")).toBeInTheDocument();
    expect(screen.getByText("0.4 / 1 vCPU")).toBeInTheDocument();
    expect(screen.getByText("% RAM")).toBeInTheDocument();
    expect(screen.getByText("25%")).toBeInTheDocument();
    expect(screen.getByText("512 MiB / 2.0 GiB")).toBeInTheDocument();
    expect(screen.getByText("% GPU")).toBeInTheDocument();
    expect(screen.getByText("% Runtime Elapsed")).toBeInTheDocument();
  });
});
