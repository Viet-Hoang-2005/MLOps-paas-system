import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { renderWithProviders } from "test/renderWithProviders";
import ExecutionTrainingJobPage from "./ExecutionTrainingJobPage";

const { flow } = vi.hoisted((): { flow: { current: Record<string, unknown> } } => ({ flow: { current: {} } }));
vi.mock("@/features/training/trainingFlowContext", () => ({ useCreateTrainingJob: () => flow.current }));
vi.mock("@/shared/hooks/useRuntimeLogStream", () => ({
  useRuntimeLogStream: () => ({ logs: [], status: null, error: null }),
}));

describe("training GPU selection", () => {
  beforeEach(() => {
    flow.current = {
      project: null, job: null, transitionState: "idle",
      executionForm: { vcpu: 2, memory_mb: 4096, max_runtime_seconds: 3600,
        accelerator_type: "none", accelerator_count: 0, accelerator_model: "" },
      setExecutionField: vi.fn(), goToStep: vi.fn(), startTraining: vi.fn(),
      refreshJob: vi.fn(), cancelTraining: vi.fn(), finishTraining: vi.fn(),
      capabilities: { enabled: true, backend: "argo", cpu_profiles: [], runtime_options_seconds: [],
        accelerators: [{ type: "none", counts: [0] }, { type: "gpu", model: "t4", counts: [1] },
          { type: "gpu", model: "a10g", counts: [1] }] },
    };
  });

  it.each(["en", "vi"] as const)("selects T4 and A10G on production in %s", async (language) => {
    renderWithProviders(<ExecutionTrainingJobPage />, { language });
    await userEvent.setup().click(screen.getByRole("button", { name: /NVIDIA T4/ }));
    expect(flow.current.setExecutionField).toHaveBeenCalledWith("accelerator_type", "gpu");
    expect(flow.current.setExecutionField).toHaveBeenCalledWith("accelerator_count", 1);
    expect(flow.current.setExecutionField).toHaveBeenCalledWith("accelerator_model", "t4");
    await userEvent.setup().click(screen.getByRole("button", { name: /NVIDIA A10G/ }));
    expect(flow.current.setExecutionField).toHaveBeenCalledWith("accelerator_model", "a10g");
    expect(screen.queryByText(/GPU ×2/)).not.toBeInTheDocument();
  });

  it("keeps a generic GPU choice for Docker", () => {
    flow.current.capabilities = { enabled: true, backend: "docker", cpu_profiles: [], runtime_options_seconds: [],
      accelerators: [{ type: "none", counts: [0] }, { type: "gpu", model: "", counts: [1] }] };
    renderWithProviders(<ExecutionTrainingJobPage />);
    expect(screen.getByRole("button", { name: /GPU ×1/ })).toBeInTheDocument();
    expect(screen.queryByText(/NVIDIA T4/)).not.toBeInTheDocument();
    expect(screen.queryByText(/NVIDIA A10G/)).not.toBeInTheDocument();
  });
});
