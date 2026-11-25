import { expect, test } from "@playwright/test";
import { installMockApi, isLiveMode } from "./fixtures/mockApi";

test.describe("Authentication & Session Guards", () => {
  test("redirects unauthenticated user from /dashboard/projects to /login", async ({
    page,
  }) => {
    if (!isLiveMode) {
      await installMockApi(page, { authenticated: false });
    }

    await page.goto("/dashboard/projects");
    await expect(page).toHaveURL(/\/login$/);
    await expect(page.locator("#input-email")).toBeVisible();
    await expect(page.locator("#input-password")).toBeVisible();
  });

  test("navigates across login, signup, and forgot-password pages", async ({
    page,
  }) => {
    if (!isLiveMode) {
      await installMockApi(page, { authenticated: false });
    }

    await page.goto("/login");
    await page.getByRole("link", { name: /forgot password/i }).click();
    await expect(page).toHaveURL(/\/forgot-password$/);

    await page.getByRole("button", { name: /back to sign in/i }).click();
    await expect(page).toHaveURL(/\/login$/);

    await page.getByRole("link", { name: /sign up/i }).click();
    await expect(page).toHaveURL(/\/signup$/);
  });

  test("shows error feedback on invalid credentials and logs in with valid credentials", async ({
    page,
  }) => {
    test.skip(isLiveMode, "Uses deterministic mock credentials");
    await installMockApi(page, { authenticated: false });

    await page.goto("/login");
    await page.locator("#input-email").fill("developer@example.com");
    await page.locator("#input-password").fill("WrongPassword!");
    await page.locator("#btn-login").click();

    await expect(page).toHaveURL(/\/login$/);
    await expect(
      page.getByText(/no active account found|incorrect/i).first(),
    ).toBeVisible();

    await page.locator("#input-password").fill("Password123!");
    await page.locator("#btn-login").click();

    await expect(page).toHaveURL(/\/dashboard\/projects$/);
    await expect(page.getByText("Diabetes-Logreg")).toBeVisible();
  });

  test("logs out from header user menu and returns to /login", async ({
    page,
  }) => {
    test.skip(isLiveMode, "Uses mocked session state");
    const state = await installMockApi(page, { authenticated: true });

    await page.goto("/dashboard/projects");
    await expect(page.getByText("Diabetes-Logreg")).toBeVisible();

    await page.getByRole("button", { name: /open user menu/i }).click();
    await page.getByRole("menuitem", { name: /logout/i }).click();

    await expect(page).toHaveURL(/\/login$/);
    expect(state.authenticated).toBe(false);
  });
});
