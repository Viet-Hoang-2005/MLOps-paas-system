import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Route, Routes } from "react-router-dom";
import { renderWithProviders } from "test/renderWithProviders";
import TrainingWorkspacePage from "./TrainingWorkspacePage";
import type { TrainingJob, TrainingRuntimeCapabilities } from "@/features/training/types";

const mocks = vi.hoisted(() => ({ get: vi.fn(), runs: vi.fn(), run: vi.fn(), input: vi.fn(), save: vi.fn(), caps: vi.fn() }));
vi.mock("react-router-dom", async (original) => ({ ...await original<typeof import("react-router-dom")>(), useBlocker: () => ({ state: "unblocked" }) }));
vi.mock("@/features/training/api/workspacesApi", async (original) => ({
  ...await original<typeof import("@/features/training/api/workspacesApi")>(),
  getWorkspace: mocks.get, listWorkspaceRuns: mocks.runs, runWorkspace: mocks.run, getRunInput: mocks.input,
}));
vi.mock("@/features/training/api/trainingApi", async (original) => ({ ...await original<typeof import("@/features/training/api/trainingApi")>(), getTrainingRuntimeCapabilities: mocks.caps }));
vi.mock("@/shared/hooks/useRuntimeLogStream", () => ({ useRuntimeLogStream: () => ({ logs: [], status: null, error: "", isPolling: false, refresh: vi.fn() }) }));
vi.mock("@/features/training/components/WorkspaceEditor", async () => {
  const { forwardRef, useImperativeHandle } = await import("react");
  return { WorkspaceEditor: forwardRef(function MockEditor({ readOnly }: { readOnly: boolean }, ref) {
    useImperativeHandle(ref, () => ({ saveAll: mocks.save }));
    return <div data-testid="workspace-editor" data-readonly={readOnly} />;
  }) };
});
const workspace = { id: "workspace", name: "Demo", revision: 1, entry_point: "train.py", entries: [], environment: {}, secrets: [], secrets_available: true };
const job = { id: "run-one", name: "Demo", project_id: null, workspace_id: "workspace", status: "running", model_flavor: "sklearn", entry_point: "train.py", requirements_text: "", vcpu: 1, memory_mb: 2048, max_runtime_seconds: 900, accelerator_type: "none", outputs: [], output_available: false, output_revision: 1 } as unknown as TrainingJob;
const caps: TrainingRuntimeCapabilities = { enabled: true, backend: "argo", runtime_options_seconds: [900, 86400], cpu_profiles: [{ id: "small", vcpu: 1, memory_mb: 2048 }], accelerators: [{ type: "none", counts: [0] }, { type: "gpu", model: "t4", counts: [1] }, { type: "gpu", model: "a10g", counts: [1] }] };
function show(language: "en" | "vi" = "en", query = "") {
  return renderWithProviders(<Routes><Route path="/training/workspaces/:workspaceId" element={<TrainingWorkspacePage />} /></Routes>, { language, initialEntries: [`/training/workspaces/workspace${query}`] });
}
describe("training workspace flow", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.get.mockResolvedValue(workspace); mocks.runs.mockResolvedValue([]); mocks.caps.mockResolvedValue(caps);
    mocks.save.mockResolvedValue(6); mocks.run.mockResolvedValue(job); mocks.input.mockResolvedValue({ entries: [], entry_point: "train.py" });
  });
  it.each(["en", "vi"] as const)("runs without a project and saves pending editor changes first in %s", async (language) => {
    show(language);
    const run = await screen.findByRole("button", { name: language === "en" ? "Run" : "Chạy" });
    await waitFor(() => expect(run).toBeEnabled());
    await userEvent.click(run);
    await waitFor(() => expect(mocks.run).toHaveBeenCalled());
    expect(mocks.save).toHaveBeenCalledOnce();
    const [id, revision, key, payload] = mocks.run.mock.calls[0];
    expect(id).toBe("workspace"); expect(revision).toBe(6); expect(key).toEqual(expect.any(String));
    expect(payload).not.toHaveProperty("project_id");
    expect(payload.source_zip).toBeNull();
    await waitFor(() => expect(screen.getByTestId("workspace-editor")).toHaveAttribute("data-readonly", "true"));
    expect(screen.getByRole("button", { name: language === "en" ? "Continue" : "Tiếp tục" })).toBeDisabled();
  });
  it("preserves the selected GPU model in the run payload", async () => {
    show();
    await screen.findByRole("button", { name: "Run" });
    await userEvent.selectOptions(screen.getByLabelText("GPU"), "a10g");
    await userEvent.click(screen.getByRole("button", { name: "Run" }));
    await waitFor(() => expect(mocks.run).toHaveBeenCalled());
    expect(mocks.run.mock.calls[0][3]).toMatchObject({ accelerator_type: "gpu", accelerator_count: 1, accelerator_model: "a10g", local_gpu_id: "" });
  });
  it("loads the selected run snapshot and enables assignment only with verified model output", async () => {
    mocks.runs.mockResolvedValue([{ ...job, status: "completed", output_available: true }]);
    show("en", "?run=run-one");
    await waitFor(() => expect(mocks.input).toHaveBeenCalledWith("run-one"));
    expect(screen.getByRole("button", { name: "Continue" })).toBeEnabled();
    expect(await screen.findByTestId("workspace-editor")).toHaveAttribute("data-readonly", "true");
  });
});
