import { Badge } from "@/shared/components/Badge";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

describe("Badge Component", () => {
  it("should render children with default neutral variant", () => {
    render(<Badge>Default Badge</Badge>);

    const badge = screen.getByText("Default Badge");
    expect(badge).toBeInTheDocument();
    expect(badge).toHaveClass("bg-surface-muted");
    expect(badge).toHaveClass("text-style-caption-strong");
  });

  it("should render specific tones correctly", () => {
    const { rerender } = render(<Badge variant="success">Completed</Badge>);
    expect(screen.getByText("Completed")).toHaveClass("text-color-success");

    rerender(<Badge variant="danger">Failed</Badge>);
    expect(screen.getByText("Failed")).toHaveClass("text-color-danger");

    rerender(<Badge variant="warning">Drift Detected</Badge>);
    expect(screen.getByText("Drift Detected")).toHaveClass("text-color-warning");
  });
});

