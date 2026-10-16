import { Search } from "@/shared/components/Search";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

describe("Search Component", () => {
  it("should render input and support typing", async () => {
    const handleChange = vi.fn();
    render(<Search placeholder="Search models..." onChange={handleChange} />);

    const input = screen.getByRole("searchbox");
    expect(input).toBeInTheDocument();
    expect(input).toHaveAttribute("placeholder", "Search models...");

    await userEvent.type(input, "churn");
    expect(handleChange).toHaveBeenCalled();
    expect(input).toHaveValue("churn");
  });

  it("should render clear button when input has value and clear on click", async () => {
    const handleClear = vi.fn();
    render(
      <Search
        placeholder="Search..."
        defaultValue="initial query"
        onClear={handleClear}
      />,
    );

    const clearButton = screen.getByRole("button", { name: /clear/i });
    expect(clearButton).toBeInTheDocument();

    await userEvent.click(clearButton);
    expect(handleClear).toHaveBeenCalled();
  });

  it("should clear input on Escape key press", async () => {
    const handleClear = vi.fn();
    render(
      <Search
        placeholder="Search..."
        defaultValue="some text"
        onClear={handleClear}
      />,
    );

    const input = screen.getByRole("searchbox");
    await userEvent.type(input, "{Escape}");
    expect(handleClear).toHaveBeenCalled();
  });
});
