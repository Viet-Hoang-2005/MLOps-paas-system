import { describe, it, expect, vi } from "vitest";
import { screen } from "@testing-library/react";
import { renderWithProviders } from "test/renderWithProviders";
import { DirectoryTree } from "./DirectoryTree";
import type { SourceTreeNode } from "@/shared/types/sourceTreeModel";

describe("DirectoryTree", () => {
  const sampleNodes: SourceTreeNode[] = [
    {
      name: "data",
      path: "data",
      type: "folder",
      children: [
        {
          name: "train.csv",
          path: "data/train.csv",
          type: "file",
          children: [],
        },
        {
          name: "raw",
          path: "data/raw",
          type: "folder",
          children: [
            {
              name: "input.json",
              path: "data/raw/input.json",
              type: "file",
              children: [],
            },
          ],
        },
      ],
    },
    {
      name: "train.py",
      path: "train.py",
      type: "file",
      children: [],
    },
  ];

  it("renders files and collapsed folder initially without indent guide", () => {
    renderWithProviders(
      <DirectoryTree
        nodes={sampleNodes}
        selectedPath={null}
        onSelect={vi.fn()}
        unsavedContents={{}}
        expandedFolders={new Set()}
        toggleFolder={vi.fn()}
      />,
    );

    expect(screen.getByText("data")).toBeInTheDocument();
    expect(screen.getByText("train.py")).toBeInTheDocument();
    expect(screen.queryByText("train.csv")).not.toBeInTheDocument();
    expect(screen.queryByTestId("indent-guide-data")).not.toBeInTheDocument();
  });

  it("renders indent guide line with correct left position when folder is expanded", () => {
    renderWithProviders(
      <DirectoryTree
        nodes={sampleNodes}
        selectedPath={null}
        onSelect={vi.fn()}
        unsavedContents={{}}
        expandedFolders={new Set(["data"])}
        toggleFolder={vi.fn()}
      />,
    );

    expect(screen.getByText("train.csv")).toBeInTheDocument();
    const guide = screen.getByTestId("indent-guide-data");
    expect(guide).toBeInTheDocument();
    // Level 0 folder: 0 * 12 + 16px = 16px
    expect(guide).toHaveStyle({ left: "16px" });
  });

  it("renders nested indent guide lines with proper indentations when subfolder is expanded", () => {
    renderWithProviders(
      <DirectoryTree
        nodes={sampleNodes}
        selectedPath={null}
        onSelect={vi.fn()}
        unsavedContents={{}}
        expandedFolders={new Set(["data", "data/raw"])}
        toggleFolder={vi.fn()}
      />,
    );

    expect(screen.getByText("input.json")).toBeInTheDocument();
    const parentGuide = screen.getByTestId("indent-guide-data");
    const childGuide = screen.getByTestId("indent-guide-data/raw");

    expect(parentGuide).toBeInTheDocument();
    expect(childGuide).toBeInTheDocument();

    // Level 0 folder: 0 * 12 + 16px = 16px
    expect(parentGuide).toHaveStyle({ left: "16px" });
    // Level 1 folder: 1 * 12 + 16px = 28px
    expect(childGuide).toHaveStyle({ left: "28px" });
  });

  it("triggers onSelect and toggleFolder on click", async () => {
    const handleSelect = vi.fn();
    const handleToggle = vi.fn();

    const { user } = renderWithProviders(
      <DirectoryTree
        nodes={sampleNodes}
        selectedPath={null}
        onSelect={handleSelect}
        unsavedContents={{}}
        expandedFolders={new Set()}
        toggleFolder={handleToggle}
      />,
    );

    await user.click(screen.getByText("data"));
    expect(handleSelect).toHaveBeenCalledWith("data");
    expect(handleToggle).toHaveBeenCalledWith("data");

    await user.click(screen.getByText("train.py"));
    expect(handleSelect).toHaveBeenCalledWith("train.py");
  });
});
