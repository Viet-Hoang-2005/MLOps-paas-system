import { screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { renderWithProviders } from "test/renderWithProviders";
import TrainingJobConfigPage from "./TrainingJobConfigPage";

const { state } = vi.hoisted(() => ({ state: { model: "t4" } }));
vi.mock("@/features/training/trainingJobDetailContext", () => ({
  useTrainingJobDetailContext: () => ({
    job: {
      backend: "argo",
      vcpu: 2,
      memory: 4096,
      max_runtime_seconds: 3600,
      accelerator_type: "gpu",
      accelerator_count: 1,
      accelerator_model: state.model,
      entry_point: "train.py",
    },
  }),
}));

describe("training configuration GPU model", () => {
  it.each([
    ["en", "t4", "NVIDIA T4"],
    ["vi", "a10g", "NVIDIA A10G"],
  ] as const)(
    "displays the selected model for %s",
    (language, model, label) => {
      state.model = model;
      renderWithProviders(<TrainingJobConfigPage />, { language });
      expect(screen.getByText(new RegExp(label))).toBeInTheDocument();
    },
  );
});
