import { expect, isLiveMode, test } from "./fixtures/auth";

test.describe("Navigation & i18n Switching", () => {
  test.skip(isLiveMode, "Uses deterministic mocked navigation endpoints");

  test("navigates across core dashboard sections without page errors", async ({
    page,
  }) => {
    const pageErrors: string[] = [];
    page.on("pageerror", (error) => pageErrors.push(error.message));

    await page.goto("/dashboard/projects");
    await expect(page.getByText("Diabetes-Logreg")).toBeVisible();

    await page.getByRole("link", { name: "Training" }).click();
    await expect(page).toHaveURL(
      /\/dashboard\/(?:projects\/[^/]+\/)?training$/,
    );

    await page.getByRole("link", { name: "Monitoring" }).click();
    await expect(page).toHaveURL(
      /\/dashboard\/(?:projects\/[^/]+\/)?monitoring$/,
    );

    await page.getByRole("link", { name: "API Keys" }).click();
    await expect(page).toHaveURL(/\/dashboard\/api-keys$/);

    expect(pageErrors).toEqual([]);
  });

  test("switches UI language between English and Vietnamese", async ({
    page,
  }) => {
    await page.goto("/dashboard/projects");
    await expect(
      page.getByRole("heading", { name: "Model Projects" }),
    ).toBeVisible();

    await page.getByRole("button", { name: /language:/i }).click();
    await page.getByRole("menuitemradio", { name: "Tiếng Việt" }).click();

    await expect(
      page.getByRole("heading", { name: "Dự án Mô hình" }),
    ).toBeVisible();

    await page.getByRole("button", { name: /ngôn ngữ:|language:/i }).click();
    await page.getByRole("menuitemradio", { name: "English" }).click();

    await expect(
      page.getByRole("heading", { name: "Model Projects" }),
    ).toBeVisible();
  });
});
