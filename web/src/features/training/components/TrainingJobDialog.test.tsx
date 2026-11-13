import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useLocation } from "react-router-dom";
import { renderWithProviders } from "test/renderWithProviders";
import { TrainingJobDialog } from "./TrainingJobDialog";

const mocks = vi.hoisted(() => ({
  list: vi.fn(),
  remove: vi.fn(),
  close: vi.fn(),
}));
vi.mock("@/features/training/api/jobWorkspaceApi", () => ({
  listWorkspaceJobs: mocks.list,
}));
vi.mock("@/features/training/api/trainingApi", () => ({
  deleteTrainingJob: mocks.remove,
}));

function Page({ currentJobId }: { currentJobId?: string }) {
  const location = useLocation();
  return (
    <>
      <span data-testid="location">{location.pathname}</span>
      <TrainingJobDialog
        workspaceId="workspace"
        currentJobId={currentJobId}
        onClose={mocks.close}
      />
    </>
  );
}

describe("TrainingJobDialog", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.list.mockResolvedValue({
      training_jobs: [
        {
          id: "job-one",
          status: "completed",
          project_name: null,
          started_at: null,
        },
      ],
      count: 1,
      page: 1,
      page_size: 20,
    });
  });
  it.each(["en", "vi"] as const)(
    "opens the selected job snapshot in %s",
    async (language) => {
      renderWithProviders(<Page />, { language });
      await userEvent.click(
        await screen.findByRole("button", { name: "job-one" }),
      );
      expect(screen.getByTestId("location")).toHaveTextContent(
        "/dashboard/training/workspaces/workspace/jobs/job-one",
      );
      expect(mocks.close).toHaveBeenCalledOnce();
      expect(mocks.remove).not.toHaveBeenCalled();
    },
  );
  it("returns to the existing workspace without creating or deleting data", async () => {
    renderWithProviders(<Page currentJobId="job-one" />, { language: "en" });
    await userEvent.click(
      screen.getByRole("button", { name: "Back to current Workspace" }),
    );
    await waitFor(() =>
      expect(screen.getByTestId("location")).toHaveTextContent(
        "/dashboard/training/workspaces/workspace",
      ),
    );
    expect(mocks.remove).not.toHaveBeenCalled();
  });
  it("disables returning when already viewing current workspace", () => {
    renderWithProviders(<Page />, { language: "en" });
    expect(
      screen.getByRole("button", { name: "Back to current Workspace" }),
    ).toBeDisabled();
  });
});
