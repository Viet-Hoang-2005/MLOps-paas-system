import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { renderWithProviders } from "test/renderWithProviders";
import { DirectoryTree } from "./DirectoryTree";

describe("DirectoryTree file actions", () => {
  it.each(["en", "vi"] as const)("opens the same edit action on double-click and selected-row button in %s", async (language) => {
    const edit = vi.fn();
    const user = userEvent.setup();
    renderWithProviders(<DirectoryTree nodes={[{ name: "train.py", path: "train.py", type: "file", children: [] }]}
      selectedPath="train.py" onSelect={vi.fn()} onEditFile={edit} unsavedContents={{}}
      expandedFolders={new Set()} toggleFolder={vi.fn()} />, { language });
    await user.dblClick(screen.getByRole("button", { name: "train.py" }));
    await user.click(screen.getByRole("button", { name: language === "vi" ? "Chỉnh sửa train.py" : "Edit train.py" }));
    expect(edit).toHaveBeenCalledTimes(2);
    expect(edit).toHaveBeenCalledWith("train.py");
  });
});
