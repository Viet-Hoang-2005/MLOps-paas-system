import { Input, InputPassword } from "@/shared/components/Input";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithProviders } from "test/renderWithProviders";
import { describe, expect, it } from "vitest";

describe("Input Component", () => {
  it("should render input with label, icon, and helper text", () => {
    renderWithProviders(
      <Input
        label="Username"
        placeholder="Enter username"
        helperText="We will never share your username"
      />,
    );

    expect(screen.getByLabelText("Username")).toBeInTheDocument();
    expect(screen.getByPlaceholderText("Enter username")).toBeInTheDocument();
    expect(
      screen.getByText("We will never share your username"),
    ).toBeInTheDocument();
  });

  it("should render error message with alert role and aria-invalid", () => {
    renderWithProviders(
      <Input label="Email" error="Invalid email address" />,
    );

    const input = screen.getByLabelText("Email");
    expect(input).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByRole("alert")).toHaveTextContent("Invalid email address");
  });
});

describe("InputPassword Component", () => {
  it("should render password input with type password initially and toggle to text on Eye click", async () => {
    renderWithProviders(
      <InputPassword label="Password" placeholder="Enter password" />,
    );

    const input = screen.getByLabelText("Password");
    expect(input).toHaveAttribute("type", "password");

    const toggleButton = screen.getByRole("button", { name: "Show password" });
    expect(toggleButton).toBeInTheDocument();

    await userEvent.click(toggleButton);

    expect(input).toHaveAttribute("type", "text");
    expect(
      screen.getByRole("button", { name: "Hide password" }),
    ).toBeInTheDocument();

    await userEvent.click(
      screen.getByRole("button", { name: "Hide password" }),
    );
    expect(input).toHaveAttribute("type", "password");
  });
});

