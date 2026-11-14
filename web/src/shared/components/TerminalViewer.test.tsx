import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { TerminalViewer } from "@/shared/components/TerminalViewer";
import { renderWithProviders } from "test/renderWithProviders";

describe("TerminalViewer Component", () => {
  it("styles completed progress indicator as white and track progress bar as light gray for pip download logs", () => {
    const pipLog =
      "  \x1b[91m━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\x1b[0m\x1b[90m╺━━━━━━━━\x1b[0m \x1b[32m232.9/297.1 MB\x1b[0m \x1b[31m5.0 MB/s\x1b[0m eta \x1b[36m0:00:13\x1b[0m";

    renderWithProviders(<TerminalViewer logs={[pipLog]} />, {
      language: "en",
    });

    const completedSpan = screen.getByText("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
    expect(completedSpan).toBeInTheDocument();
    expect(completedSpan).toHaveClass("text-color-terminal-foreground");
    expect(completedSpan.style.color).toBe("");

    const trackSpan = screen.getByText("╺━━━━━━━━");
    expect(trackSpan).toBeInTheDocument();
    expect(trackSpan).toHaveClass("text-color-terminal-muted");
    expect(trackSpan.style.color).toBe("");

    const sizeSpan = screen.getByText("232.9/297.1 MB");
    expect(sizeSpan).toBeInTheDocument();
    expect(sizeSpan.style.color).toBe("rgb(0, 187, 0)");
  });

  it("handles plain text pip progress bars by splitting completed and track segments", () => {
    const plainPipLog =
      "  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╺━━━━━━━━ 232.9/297.1 MB 5.0 MB/s eta 0:00:13";

    renderWithProviders(<TerminalViewer logs={[plainPipLog]} />, {
      language: "en",
    });

    const completedSpan = screen.getByText("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
    expect(completedSpan).toHaveClass("text-color-terminal-foreground");

    const trackSpan = screen.getByText("╺━━━━━━━━");
    expect(trackSpan).toHaveClass("text-color-terminal-muted");

    expect(
      screen.getByText(/232\.9\/297\.1 MB 5\.0 MB\/s eta 0:00:13/),
    ).toBeInTheDocument();
  });

  it("renders 100% completed pip download bar in white", () => {
    const fullLog =
      "  \x1b[91m━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\x1b[0m \x1b[32m297.1/297.1 MB\x1b[0m";

    renderWithProviders(<TerminalViewer logs={[fullLog]} />, {
      language: "en",
    });

    const completedSpan = screen.getByText(
      "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
    );
    expect(completedSpan).toHaveClass("text-color-terminal-foreground");
  });

  it("renders 0% pip download bar in light gray track", () => {
    const zeroLog =
      "  \x1b[90m╺━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\x1b[0m \x1b[32m0.0/297.1 MB\x1b[0m";

    renderWithProviders(<TerminalViewer logs={[zeroLog]} />, {
      language: "en",
    });

    const trackSpan = screen.getByText(
      "╺━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
    );
    expect(trackSpan).toHaveClass("text-color-terminal-muted");
  });

  it("renders standard ANSI log lines without altering regular colors", () => {
    const normalLogs = [
      "Training runner execution started",
      "Installing requirements.txt",
      "Collecting xgboost==2.0.3",
      "Downloading xgboost-2.0.3-py3-none-manylinux2014_x86_64.whl (297.1 MB)",
    ];

    renderWithProviders(<TerminalViewer logs={normalLogs} />, {
      language: "en",
    });

    expect(
      screen.getByText("Training runner execution started"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Installing requirements.txt"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Collecting xgboost==2.0.3"),
    ).toBeInTheDocument();
  });

  it("copies logs to clipboard when copy button is clicked", async () => {
    const user = userEvent.setup();
    const writeTextSpy = vi
      .spyOn(navigator.clipboard, "writeText")
      .mockResolvedValue();

    renderWithProviders(
      <TerminalViewer
        logs={["Line 1", "Line 2"]}
        title="Training logs"
      />,
      { language: "en" },
    );

    const copyBtn = screen.getByRole("button", { name: /copy/i });
    await user.click(copyBtn);

    expect(writeTextSpy).toHaveBeenCalledWith("Line 1\nLine 2");
  });
});

