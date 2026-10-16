import { Slider } from "@/shared/components/Slider";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

describe("Slider Component", () => {
  const options = [500, 1000, 2000, 5000, 10000, 20000].map((value) => ({
    value,
    label: String(value),
  }));

  it("should render range input with accessible attributes and tick buttons", () => {
    render(
      <Slider
        options={options}
        value={1000}
        onChange={vi.fn()}
        ariaLabel="Trigger threshold"
      />,
    );

    const rangeInput = screen.getByRole("slider", { name: "Trigger threshold" });
    expect(rangeInput).toBeInTheDocument();
    expect(rangeInput).toHaveAttribute("type", "range");
    expect(rangeInput).toHaveAttribute("aria-valuetext", "1000");

    const tickButtons = screen.getAllByRole("button");
    expect(tickButtons.length).toBe(6);

    const activeTick = screen.getByRole("button", { name: "1000" });
    expect(activeTick).toHaveAttribute("aria-pressed", "true");
  });

  it("should trigger onChange when clicking tick buttons", async () => {
    const handleChange = vi.fn();
    render(
      <Slider
        options={options}
        value={1000}
        onChange={handleChange}
        ariaLabel="Trigger threshold"
      />,
    );

    const tick5000 = screen.getByRole("button", { name: "5000" });
    await userEvent.click(tick5000);
    expect(handleChange).toHaveBeenCalledWith(5000);
  });

  it("should respect disabled state without NaN or Infinity in styles", () => {
    const { container } = render(
      <Slider
        options={[options[0]]}
        value={500}
        onChange={vi.fn()}
        disabled
      />,
    );

    const slider = screen.getByRole("slider");
    expect(slider).toBeDisabled();
    expect(container.innerHTML).not.toMatch(/NaN|Infinity/);
  });
});

