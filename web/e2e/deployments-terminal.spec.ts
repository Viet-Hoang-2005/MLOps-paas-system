import { expect, isLiveMode, test } from "./fixtures/auth";

test.describe("Deployments & TerminalViewer Progress Bar", () => {
  test.skip(isLiveMode, "Uses deterministic build log stream mock");

  test("updates TERMINAL_PROGRESS bar in place without duplicating lines", async ({
    page,
    mockApi,
  }) => {
    let poll = 0;
    mockApi.onBuildLogRequest = (_pollNumber, buildId) => {
      poll += 1;
      if (poll === 1) {
        return {
          logs: [
            "Starting BUILD process",
            "Downloading scikit_learn-1.6.1.whl (13.1 MB)",
            `TERMINAL_PROGRESS ${JSON.stringify({
              text: "\u001b[91m━━━━━━━━\u001b[90m━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\u001b[0m \u001b[32m2.6/13.1 MB\u001b[0m",
              done: false,
            })}`,
          ],
          next_offset: 3,
          status: "building",
          error_message: "",
        };
      }

      mockApi.builds[buildId].status = "ready";
      mockApi.builds[buildId].image_uri =
        "mlops-paas-serving/project-diabetes:v1";

      return {
        logs: [
          `TERMINAL_PROGRESS ${JSON.stringify({
            text: "\u001b[92m━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\u001b[0m \u001b[32m13.1/13.1 MB\u001b[0m",
            done: true,
          })}`,
          "Build completed.",
        ],
        next_offset: 5,
        status: "ready",
        error_message: "",
      };
    };

    await page.goto(
      "/dashboard/deployment/build/new?projectId=project-diabetes&buildId=build-1",
    );

    await expect(page.getByText("Starting BUILD process")).toBeVisible();
    await expect(page.getByText("2.6/13.1 MB")).toBeVisible();

    await expect(page.getByText("13.1/13.1 MB")).toBeVisible({
      timeout: 10_000,
    });
    await expect(page.getByText("2.6/13.1 MB")).toHaveCount(0);
    await expect(page.getByText("Build completed.")).toBeVisible();
  });
});
