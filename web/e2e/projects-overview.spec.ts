import { expect, isLiveMode, test } from "./fixtures/auth";

test.describe("Model Projects & Overview", () => {
  test.skip(isLiveMode, "Runs against deterministic mocked Control Plane API");

  test("lists projects, filters by search, and clears search", async ({
    page,
    mockApi,
  }) => {
    expect(mockApi.projects.length).toBeGreaterThanOrEqual(2);
    await page.goto("/dashboard/projects");

    await expect(page.getByText("Diabetes-Logreg")).toBeVisible();
    await expect(page.getByText("BAF-Fraud-Detector")).toBeVisible();

    const searchInput = page.getByPlaceholder("Search model projects...");
    await searchInput.fill("BAF");
    await expect(page.getByText("BAF-Fraud-Detector")).toBeVisible();
    await expect(page.getByText("Diabetes-Logreg")).toBeHidden();

    await searchInput.fill("nonexistent-model");
    await expect(
      page.getByText("No matching model projects found."),
    ).toBeVisible();

    await page.getByRole("button", { name: "Clear search" }).click();
    await expect(page.getByText("Diabetes-Logreg")).toBeVisible();
  });

  test("recovers from transient project list failure via retry button", async ({
    page,
    mockApi,
  }) => {
    mockApi.listProjectsFailureCount = 3;

    await page.goto("/dashboard/projects");
    const alert = page.getByRole("alert");
    await expect(alert).toBeVisible();
    await expect(alert).toContainText(/temporary database outage|failed/i);

    mockApi.listProjectsFailureCount = 0;
    await page.getByRole("button", { name: "Try again" }).click();
    await expect(page.getByText("Diabetes-Logreg")).toBeVisible();
  });

  test("creates a new model project and navigates to overview", async ({
    page,
  }) => {
    await page.goto("/dashboard/projects");
    await page.getByRole("button", { name: "New model project" }).click();
    await expect(page).toHaveURL(/\/dashboard\/projects\/new$/);

    await page.locator("#metadata-name").fill("Credit-Risk-XGB");
    await page
      .locator("#metadata-description")
      .fill("Credit risk model created from Playwright E2E");

    const fileInput = page.locator('input[type="file"]').first();
    await fileInput.setInputFiles({
      name: "model.joblib",
      mimeType: "application/octet-stream",
      buffer: Buffer.from("mock-joblib-binary"),
    });

    const saveBtn = page.getByRole("button", { name: "Save Preview" });
    await expect(saveBtn).toBeEnabled();
    await saveBtn.click();

    await expect(page).toHaveURL(/\/dashboard\/projects\/project-created\/overview$/);
    await expect(page.getByText("Credit-Risk-XGB").first()).toBeVisible();
  });

  test("renders ModelStatusLine and runtime logs on running project overview", async ({
    page,
    mockApi,
  }) => {
    await page.goto("/dashboard/projects/project-diabetes/overview");

    await expect(page.getByText("Model status")).toBeVisible();
    await expect(page.getByText("API health: Healthy").first()).toBeVisible();
    await expect(
      page.getByText("Uvicorn running on http://0.0.0.0:5001"),
    ).toBeVisible();
    await expect(page.getByText("Model artifact loaded")).toBeVisible();

    mockApi.runtimeLogsError = true;
    await page.reload();
    await expect(page.getByText("Runtime logs unavailable")).toBeVisible();
  });
});
