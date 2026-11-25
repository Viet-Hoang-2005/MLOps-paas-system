import { defineConfig, devices } from "@playwright/test";

const liveBaseURL = process.env.PLAYWRIGHT_BASE_URL?.trim();
const localServerURL = "http://127.0.0.1:4173";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : 3,
  timeout: 30_000,
  expect: {
    timeout: 15_000,
  },
  reporter: process.env.CI
    ? [["github"], ["html", { open: "never" }], ["list"]]
    : [["list"], ["html", { open: "never" }]],
  use: {
    baseURL: liveBaseURL || localServerURL,
    trace: "on-first-retry",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  webServer: liveBaseURL
    ? undefined
    : {
        command: process.env.CI
          ? "pnpm exec vite preview --host 127.0.0.1 --port 4173 --strictPort"
          : "pnpm exec vite --host 127.0.0.1 --port 4173 --strictPort",
        url: localServerURL,
        reuseExistingServer: !process.env.CI,
        timeout: 60_000,
      },
});
