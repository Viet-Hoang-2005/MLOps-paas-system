import * as useModelProjectsHook from "@/features/projects/hooks/useModelProjects";
import type { ModelProject } from "@/features/projects/types";
import ProjectRouteBoundary from "@/app/router/ProjectRouteBoundary";
import { renderWithProviders } from "test/renderWithProviders";
import { screen } from "@testing-library/react";
import { Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { createMockProject } from "test/fixtures/models";

describe("ProjectRouteBoundary Component", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("should render NotFoundPage when modelId does not exist in project list", () => {
    vi.spyOn(useModelProjectsHook, "useModelProjects").mockReturnValue({
      isPending: false,
      isError: false,
      data: {
        models: [
          createMockProject({
            id: "existing-proj-1",
            name: "Model One",
          }) as unknown as ModelProject,
        ],
        selectedModel: null,
      },
    } as unknown as ReturnType<typeof useModelProjectsHook.useModelProjects>);

    renderWithProviders(
      <Routes>
        <Route path="/projects/:modelId" element={<ProjectRouteBoundary />}>
          <Route index element={<div>Project Detail Outlet</div>} />
        </Route>
      </Routes>,
      { initialEntries: ["/projects/non-existent-proj"] },
    );

    expect(screen.queryByText("Project Detail Outlet")).not.toBeInTheDocument();
  });

  it("should render Outlet when modelId matches a registered project", () => {
    vi.spyOn(useModelProjectsHook, "useModelProjects").mockReturnValue({
      isPending: false,
      isError: false,
      data: {
        models: [
          createMockProject({
            id: "proj-123",
            name: "Churn Model",
          }) as unknown as ModelProject,
        ],
        selectedModel: null,
      },
    } as unknown as ReturnType<typeof useModelProjectsHook.useModelProjects>);

    renderWithProviders(
      <Routes>
        <Route path="/projects/:modelId" element={<ProjectRouteBoundary />}>
          <Route index element={<div>Project Detail Outlet</div>} />
        </Route>
      </Routes>,
      { initialEntries: ["/projects/proj-123"] },
    );

    expect(screen.getByText("Project Detail Outlet")).toBeInTheDocument();
  });
});
