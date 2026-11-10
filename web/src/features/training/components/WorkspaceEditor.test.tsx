import { createRef } from "react";
import { act, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { renderWithProviders } from "test/renderWithProviders";
import { WorkspaceEditor, type WorkspaceEditorHandle } from "./WorkspaceEditor";
import type { TrainingWorkspace } from "@/features/training/api/workspacesApi";

const mocks = vi.hoisted(() => ({ read: vi.fn(), save: vi.fn() }));
vi.mock("@/features/training/api/workspacesApi", async (original) => ({ ...await original<typeof import("@/features/training/api/workspacesApi")>(), readEntry: mocks.read, saveWorkspaceEntry: mocks.save }));
vi.mock("@/shared/components/CodeViewer", () => ({ CodeViewer: ({ value, onChange, options }: { value: string; onChange: (value: string) => void; options: { readOnly: boolean } }) => <textarea aria-label="test-editor" value={value} readOnly={options.readOnly} onChange={(event) => onChange(event.target.value)} /> }));
const workspace: TrainingWorkspace = { id: "workspace", revision: 1, entry_point: "train.py", environment: {}, secrets: [], secrets_available: true, entries: [{ id: "file", path: "train.py", kind: "script", size_bytes: 8, download_url: "https://example.test/file" }] };
describe("workspace file editor", () => {
  beforeEach(() => { vi.clearAllMocks(); mocks.read.mockResolvedValue("print(1)"); mocks.save.mockResolvedValue({ revision: 2, entry: workspace.entries[0] }); });
  it("saves unsaved content before exposing a revision for Run", async () => {
    const ref = createRef<WorkspaceEditorHandle>();
    renderWithProviders(<WorkspaceEditor ref={ref} workspace={workspace} entries={workspace.entries} entryPoint="train.py" readOnly={false} onDirty={vi.fn()} onBusy={vi.fn()} onRefresh={() => Promise.resolve({ ...workspace, revision: 2 })} />);
    await userEvent.click(screen.getByRole("button", { name: "train.py" }));
    await waitFor(() => expect(screen.getByLabelText("test-editor")).toHaveValue("print(1)"));
    await userEvent.clear(screen.getByLabelText("test-editor"));
    await userEvent.type(screen.getByLabelText("test-editor"), "print(2)");
    let revision;
    await act(async () => { revision = await ref.current!.saveAll(); });
    expect(revision).toBe(2);
    expect(mocks.save).toHaveBeenCalledWith("workspace", 1, { path: "train.py", kind: "script", file: null }, "file", "print(2)");
  });
  it("disables mutation actions for read-only input", () => {
    renderWithProviders(<WorkspaceEditor workspace={workspace} entries={workspace.entries} entryPoint="train.py" readOnly onDirty={vi.fn()} onBusy={vi.fn()} onRefresh={() => Promise.resolve(workspace)} />);
    expect(screen.getByRole("button", { name: "New file" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "New folder" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Delete" })).toBeDisabled();
  });
});
