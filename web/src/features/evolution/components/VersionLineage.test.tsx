import { VersionLineage } from "@/features/evolution/components/VersionLineage";
import type { ModelVersion } from "@/features/projects/types";
import { renderWithProviders } from "test/renderWithProviders";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

describe("VersionLineage Component", () => {
  const v1 = {
    id: "1",
    version: "v1",
    registered_at: "2026-01-01T00:00:00Z",
  } as unknown as ModelVersion;
  const v2 = {
    id: "2",
    version: "v2",
    registered_at: "2026-01-02T00:00:00Z",
  } as unknown as ModelVersion;

  it("should render lineage versions with running status and aria-current", () => {
    renderWithProviders(
      <VersionLineage
        versions={[v2, v1]}
        selectedId="1"
        runningId="1"
        onSelect={vi.fn()}
      />,
      { language: "en" },
    );

    const v1Button = screen.getByRole("button", { name: /v1/i });
    expect(v1Button).toHaveAttribute("aria-current", "true");
    expect(screen.getByText(/running/i)).toBeInTheDocument();
  });

  it("should render localized running status in Vietnamese", () => {
    renderWithProviders(
      <VersionLineage
        versions={[v2, v1]}
        selectedId="1"
        runningId="1"
        onSelect={vi.fn()}
      />,
      { language: "vi" },
    );

    expect(screen.getByText(/đang chạy/i)).toBeInTheDocument();
  });

  it("should trigger onSelect when clicking a different version", async () => {
    const handleSelect = vi.fn();
    renderWithProviders(
      <VersionLineage
        versions={[v2, v1]}
        selectedId="1"
        runningId="1"
        onSelect={handleSelect}
      />,
    );

    const v2Button = screen.getByRole("button", { name: /v2/i });
    await userEvent.click(v2Button);
    expect(handleSelect).toHaveBeenCalledWith(v2.id);
  });
});
