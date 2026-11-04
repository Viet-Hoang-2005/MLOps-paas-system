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
        accelerator_type: "none", accelerator_count: 0, accelerator_model: "", local_gpu_id: "" },
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

  it("lists detected NVIDIA devices and allows rechecking Docker", async () => {
    const gpuId = "GPU-01234567-89ab-cdef-0123-456789abcdef";
    flow.current.refreshGpuCapabilities = vi.fn();
    flow.current.capabilities = { enabled: true, backend: "docker", cpu_profiles: [], runtime_options_seconds: [],
      accelerators: [{ type: "none", counts: [0] }, { type: "gpu", model: "", device_id: gpuId, counts: [1] }],
      local_gpu: { status: "available", reason: "", devices: [{ id: gpuId, name: "NVIDIA Test",
        memory_total_mib: 8192, memory_free_mib: 6144 }] } };
    renderWithProviders(<ExecutionTrainingJobPage />);
    expect(screen.getByText(/8192 MiB total/)).toBeInTheDocument();
    expect(screen.getByText(/6144 MiB free/)).toBeInTheDocument();
    await userEvent.setup().click(screen.getByRole("button", { name: /NVIDIA Test/ }));
    expect(flow.current.setExecutionField).toHaveBeenCalledWith("local_gpu_id", gpuId);
    await userEvent.setup().click(screen.getByRole("button", { name: "Check GPU again" }));
    expect(flow.current.refreshGpuCapabilities).toHaveBeenCalledOnce();
    expect(screen.queryByText(/NVIDIA T4/)).not.toBeInTheDocument();
    expect(screen.queryByText(/NVIDIA A10G/)).not.toBeInTheDocument();
  });

  it("keeps CPU available and explains an unavailable GPU", () => {
    flow.current.refreshGpuCapabilities = vi.fn();
    flow.current.capabilities = { enabled: true, backend: "docker", cpu_profiles: [], runtime_options_seconds: [],
      accelerators: [{ type: "none", counts: [0] }],
      local_gpu: { status: "unavailable", reason: "nvidia_unavailable", devices: [] } };
    renderWithProviders(<ExecutionTrainingJobPage />);
    expect(screen.getByRole("button", { name: /CPU only/ })).toBeInTheDocument();
    expect(screen.getByText(/NVIDIA driver and container toolkit/)).toBeInTheDocument();
  });
});
