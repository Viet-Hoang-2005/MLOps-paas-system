import { screen } from "@testing-library/react";
import { Plus } from "lucide-react";
import { Link } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { renderWithProviders } from "test/renderWithProviders";
import { Button } from "./Button";

describe("Button", () => {
  it("supports asChild without prefix nodes", () => {
    renderWithProviders(
      <Button asChild variant="secondary" size="sm">
        <Link to="/dashboard/training">Training job</Link>
      </Button>,
    );

    const link = screen.getByRole("link", { name: "Training job" });
    expect(link).toHaveAttribute("href", "/dashboard/training");
  });

  it("supports asChild with an icon via Slottable", () => {
    renderWithProviders(
      <Button asChild icon={<Plus data-testid="btn-icon" />}>
        <Link to="/dashboard/projects">Open</Link>
      </Button>,
    );

    const link = screen.getByRole("link", { name: "Open" });
    expect(link).toHaveAttribute("href", "/dashboard/projects");
    expect(screen.getByTestId("btn-icon")).toBeInTheDocument();
  });
});
