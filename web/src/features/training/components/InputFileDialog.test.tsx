import { describe, it, expect, vi } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { InputFileDialog } from "./InputFileDialog";
import { renderWithProviders } from "test/renderWithProviders";

describe("InputFileDialog - File Extension Auto-mapping and Validation", () => {
  it("auto-maps extension when user does not enter extension (e.g. 'train' -> 'train.py')", async () => {
    const user = userEvent.setup();
    const handleSave = vi.fn();
    const handleClose = vi.fn();

    renderWithProviders(
      <InputFileDialog
        hasRequirements={false}
        onClose={handleClose}
        onSave={handleSave}
      />
    );

    const nameInput = screen.getByLabelText(/File name/i);
    await user.clear(nameInput);
    await user.type(nameInput, "train");

    const submitButton = screen.getByRole("button", { name: /^Create$/i });
    await user.click(submitButton);

    expect(handleSave).toHaveBeenCalledWith({
      kind: "script",
      path: "train.py",
      file: null,
    });
  });

  it("allows creation when user includes matching extension (e.g. 'train.py' for script)", async () => {
    const user = userEvent.setup();
    const handleSave = vi.fn();
    const handleClose = vi.fn();

    renderWithProviders(
      <InputFileDialog
        hasRequirements={false}
        onClose={handleClose}
        onSave={handleSave}
      />
    );

    const nameInput = screen.getByLabelText(/File name/i);
    await user.clear(nameInput);
    await user.type(nameInput, "train.py");

    const submitButton = screen.getByRole("button", { name: /^Create$/i });
    await user.click(submitButton);

    expect(handleSave).toHaveBeenCalledWith({
      kind: "script",
      path: "train.py",
      file: null,
    });
  });

  it("rejects creation and shows error when user includes mismatched extension (e.g. 'train.csv' for script)", async () => {
    const user = userEvent.setup();
    const handleSave = vi.fn();
    const handleClose = vi.fn();

    renderWithProviders(
      <InputFileDialog
        hasRequirements={false}
        onClose={handleClose}
        onSave={handleSave}
      />
    );

    const nameInput = screen.getByLabelText(/File name/i);
    await user.clear(nameInput);
    await user.type(nameInput, "train.csv");

    const submitButton = screen.getByRole("button", { name: /^Create$/i });
    await user.click(submitButton);

    expect(handleSave).not.toHaveBeenCalled();
    expect(
      screen.getByText(/Enter a valid name with the selected extension/i)
    ).toBeInTheDocument();
  });

  it("rejects trailing dot or leading dot without basename", async () => {
    const user = userEvent.setup();
    const handleSave = vi.fn();
    const handleClose = vi.fn();

    renderWithProviders(
      <InputFileDialog
        hasRequirements={false}
        onClose={handleClose}
        onSave={handleSave}
      />
    );

    const nameInput = screen.getByLabelText(/File name/i);
    await user.clear(nameInput);
    await user.type(nameInput, "train.");

    const submitButton = screen.getByRole("button", { name: /^Create$/i });
    await user.click(submitButton);

    expect(handleSave).not.toHaveBeenCalled();
    expect(
      screen.getByText(/Enter a valid name with the selected extension/i)
    ).toBeInTheDocument();
  });

  it("handles parentPath correctly when auto-mapping extension", async () => {
    const user = userEvent.setup();
    const handleSave = vi.fn();
    const handleClose = vi.fn();

    renderWithProviders(
      <InputFileDialog
        parentPath="src/models"
        hasRequirements={false}
        onClose={handleClose}
        onSave={handleSave}
      />
    );

    const nameInput = screen.getByLabelText(/File name/i);
    await user.clear(nameInput);
    await user.type(nameInput, "classifier");

    const submitButton = screen.getByRole("button", { name: /^Create$/i });
    await user.click(submitButton);

    expect(handleSave).toHaveBeenCalledWith({
      kind: "script",
      path: "src/models/classifier.py",
      file: null,
    });
  });
});
