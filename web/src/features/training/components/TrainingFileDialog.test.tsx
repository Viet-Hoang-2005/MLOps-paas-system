import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { renderWithProviders } from "test/renderWithProviders";
import { TrainingFileDialog } from "./TrainingFileDialog";

describe("TrainingFileDialog", () => {
  it.each(["en", "vi"] as const)("requires CSV upload and creates a data file in %s", async (language) => {
    const onSave = vi.fn();
    const user = userEvent.setup();
    renderWithProviders(<TrainingFileDialog hasRequirements={false} onClose={vi.fn()} onSave={onSave} />, { language });
    await user.selectOptions(screen.getByRole("combobox"), "data");
    await user.type(screen.getByLabelText(language === "vi" ? "Tên tệp" : "File name"), "train.csv");
    await user.click(screen.getByRole("button", { name: language === "vi" ? "Tạo" : "Create" }));
    expect(onSave).not.toHaveBeenCalled();
    const upload = document.querySelector('input[type="file"]') as HTMLInputElement;
    const file = new File(["x\n1\n"], "train.csv", { type: "text/csv" });
    await user.upload(upload, file);
    await user.click(screen.getByRole("button", { name: language === "vi" ? "Tạo" : "Create" }));
    expect(onSave).toHaveBeenCalledWith({ kind: "data", path: "train.csv", file });
  });

  it("keeps existing requirements fixed and disables creation when one exists", () => {
    renderWithProviders(<TrainingFileDialog hasRequirements onClose={vi.fn()} onSave={vi.fn()} />);
    expect(screen.getByRole("option", { name: /Requirements/ })).toBeDisabled();
  });

  it("locks an existing requirements file and hides replacement upload", () => {
    renderWithProviders(<TrainingFileDialog hasRequirements existing={{ kind: "requirements", path: "requirements.txt" }} onClose={vi.fn()} onSave={vi.fn()} />);
    expect(screen.getByLabelText("File name")).toHaveValue("requirements.txt");
    expect(screen.getByLabelText("File name")).toBeDisabled();
    expect(screen.getByLabelText("File type")).toBeDisabled();
    expect(document.querySelector('input[type="file"]')).toBeNull();
  });
});
