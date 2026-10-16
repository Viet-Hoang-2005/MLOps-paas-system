import { Chart } from "@/shared/components/Chart";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

describe("Chart Component", () => {
  it("should render empty state message when data is empty", () => {
    render(<Chart data={[]} emptyText="No metrics available" />);
    expect(screen.getByText("No metrics available")).toBeInTheDocument();
  });

  it("should safely handle negative metrics without NaN or Infinity", () => {
    const { container } = render(
      <Chart
        data={[
          { timestamp: 0, value: -1 },
          { timestamp: 1, value: -1 },
        ]}
        allowNegative
      />,
    );

    expect(container.innerHTML).not.toMatch(/NaN|Infinity/);
  });

  it("should display negative scale labels when allowNegative is enabled", () => {
    const { container } = render(
      <Chart
        data={[
          { timestamp: 0, value: -2 },
          { timestamp: 1, value: -1 },
        ]}
        allowNegative
      />,
    );

    expect(container.innerHTML).toMatch(/>-2/);
    expect(container.innerHTML).not.toMatch(/NaN|Infinity/);
  });
});

