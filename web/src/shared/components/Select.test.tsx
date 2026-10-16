import { Select, type SelectOption } from "@/shared/components/Select";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

describe("Select Component", () => {
  const options: SelectOption[] = [
    { value: "opt-1", label: "Option One" },
    { value: "opt-2", label: "Option Two", badge: <span>New</span> },
    { value: "opt-3", label: "Option Three" },
  ];

  it("should render placeholder when no option is selected", () => {
    render(
      <Select
        value=""
        onChange={vi.fn()}
        options={options}
        placeholder="Choose an option"
      />,
    );

    expect(screen.getByText("Choose an option")).toBeInTheDocument();
  });

  it("should render selected option label and badge", () => {
    render(
      <Select value="opt-2" onChange={vi.fn()} options={options} />,
    );

    expect(screen.getByText("Option Two")).toBeInTheDocument();
    expect(screen.getByText("New")).toBeInTheDocument();
  });

  it("should open popover on click and select new option", async () => {
    const handleChange = vi.fn();
    render(
      <Select value="opt-1" onChange={handleChange} options={options} />,
    );

    const trigger = screen.getByRole("button");
    await userEvent.click(trigger);

    const optionThree = await screen.findByRole("button", { name: /Option Three/ });
    expect(optionThree).toBeInTheDocument();

    await userEvent.click(optionThree);
    expect(handleChange).toHaveBeenCalledWith("opt-3");
  });
});

