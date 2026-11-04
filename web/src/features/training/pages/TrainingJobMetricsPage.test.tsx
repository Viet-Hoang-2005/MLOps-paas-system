import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { renderWithProviders } from "test/renderWithProviders";
import TrainingJobMetricsPage from "./TrainingJobMetricsPage";

const { context } = vi.hoisted((): { context: { current: Record<string, unknown> } } => ({ context: { current: {} } }));
vi.mock("@/features/training/trainingJobDetailContext", () => ({ useTrainingJobDetailContext: () => context.current }));
vi.mock("@/features/training/components/TrainingJobModelMetrics", () => ({ TrainingJobModelMetrics: () => null }));

describe("training runtime metrics", () => {
  beforeEach(() => {
    context.current = {
      job: { id: "job", status: "running" }, activeStatuses: ["running", "queued"],
      refreshMetrics: vi.fn(), loadingMetrics: false, refreshingSection: null,
      metrics: { status: "available", latest: { timestamp: "2026-01-01T00:00:00Z",
        cpu_percent: 40, cpu_limit_cores: 2, memory_percent: 30, memory_used_mb: 1024, memory_limit_mb: 4096,
        gpu_percent: 60, gpu_memory_used_mb: 2048, gpu_memory_total_mb: 8192, gpu_memory_percent: 25 } },
    };
  });

  it.each(["en", "vi"] as const)("shows all four values in %s and refreshes", async (language) => {
    renderWithProviders(<TrainingJobMetricsPage />, { language });
    for (const value of ["40%", "30%", "60%", "25%"]) expect(screen.getByText(value)).toBeInTheDocument();
    expect(screen.getByText(/2[.,]0 GiB \/ 8[.,]0 GiB/)).toBeInTheDocument();
    await userEvent.setup().click(screen.getByRole("button", { name: language === "en" ? "Refresh" : "Làm mới" }));
    expect(context.current.refreshMetrics).toHaveBeenCalledOnce();
  });

  it("shows unavailable GPU values without hiding CPU", () => {
    const current = context.current.metrics as { latest: Record<string, unknown> };
    Object.assign(current.latest, { gpu_percent: null, gpu_memory_percent: null });
    renderWithProviders(<TrainingJobMetricsPage />);
    expect(screen.getByText("40%")).toBeInTheDocument();
    expect(screen.getAllByText("Not available")).toHaveLength(2);
  });

  it("hides old measurements when the job finishes", () => {
    context.current.job = { id: "job", status: "completed" };
    renderWithProviders(<TrainingJobMetricsPage />);
    expect(screen.queryByText("40%")).not.toBeInTheDocument();
    expect(screen.getByText(/available while the job is running/)).toBeInTheDocument();
  });

  it("reports a failed fetch rather than displaying stale data", () => {
    context.current.metricsError = true;
    renderWithProviders(<TrainingJobMetricsPage />);
    expect(screen.queryByText("40%")).not.toBeInTheDocument();
    expect(screen.getByText(/temporarily unavailable/)).toBeInTheDocument();
  });
});
