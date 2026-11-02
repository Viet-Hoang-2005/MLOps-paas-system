import { Back } from "@/shared/components/Back";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithProviders } from "test/renderWithProviders";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mockNavigate = vi.fn();
vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual("react-router-dom");
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

describe("Back Component", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("should render icon button when title is omitted and navigate(-1) on click", async () => {
    renderWithProviders(<Back />);

    const button = screen.getByRole("button", { name: "Back" });
    expect(button).toBeInTheDocument();

    await userEvent.click(button);
    expect(mockNavigate).toHaveBeenCalledWith(-1);
  });

  it("should render with title and navigate(-1) on click by default", async () => {
    renderWithProviders(<Back title="Back to sign in" />);

    const button = screen.getByRole("button", { name: "Back to sign in" });
    expect(button).toBeInTheDocument();
    expect(screen.getByText("Back to sign in")).toBeInTheDocument();

    await userEvent.click(button);
    expect(mockNavigate).toHaveBeenCalledWith(-1);
  });

  it("should execute custom onBack callback when provided instead of navigate", async () => {
    const handleCustomBack = vi.fn();
    renderWithProviders(
      <Back title="Custom Back" onBack={handleCustomBack} />,
    );

    const button = screen.getByRole("button", { name: "Custom Back" });
    await userEvent.click(button);

    expect(handleCustomBack).toHaveBeenCalledTimes(1);
    expect(mockNavigate).not.toHaveBeenCalled();
  });

  it("should navigate to specified route when `to` prop is provided", async () => {
    renderWithProviders(<Back to="/login" title="Sign in" />);

    const button = screen.getByRole("button", { name: "Sign in" });
    await userEvent.click(button);

    expect(mockNavigate).toHaveBeenCalledWith("/login");
  });

  it("should render element title alongside button when React element is provided", () => {
    renderWithProviders(
      <Back
        title={<h1 data-testid="page-heading">My Page</h1>}
        onBack={vi.fn()}
      />,
    );

    expect(screen.getByTestId("page-heading")).toHaveTextContent("My Page");
    expect(screen.getByRole("button", { name: "Back" })).toBeInTheDocument();
  });
});
