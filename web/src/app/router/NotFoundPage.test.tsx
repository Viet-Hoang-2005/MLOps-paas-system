import { describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithProviders } from "test/renderWithProviders";
import NotFoundPage from "./NotFoundPage";

const mockNavigate = vi.fn();
vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual<typeof import("react-router-dom")>("react-router-dom");
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

describe("NotFoundPage Component", () => {
  it("renders placeholder with 404 title, description and fallback button", async () => {
    const user = userEvent.setup();
    renderWithProviders(<NotFoundPage />);

    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(screen.getByText("404 Not found")).toBeInTheDocument();
    expect(screen.getByText("This page or model project does not exist.")).toBeInTheDocument();

    const fallbackBtn = screen.getByRole("button", { name: "Model Projects" });
    expect(fallbackBtn).toBeInTheDocument();

    await user.click(fallbackBtn);
    expect(mockNavigate).toHaveBeenCalledWith("/dashboard/projects");
  });
});
