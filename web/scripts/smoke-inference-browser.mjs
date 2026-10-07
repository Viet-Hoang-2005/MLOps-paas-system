import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { fileURLToPath, pathToFileURL } from "node:url";
import path from "node:path";

const { chromium } = await import(
  pathToFileURL(process.env.P1_PLAYWRIGHT_MODULE).href
);
const root = fileURLToPath(new URL("../../", import.meta.url));
const docker = (args) =>
  execFileSync("docker", args, {
    encoding: "utf8",
    stdio: ["ignore", "pipe", "pipe"],
  });
const fixture = JSON.parse(
  docker([
    "exec",
    "control_plane",
    "python",
    "manage.py",
    "shell",
    "-c",
    "exec(open('scripts/p1_inference_fixture.py').read())",
  ]),
);
const browser = await chromium.launch({ headless: true });
const runtimes = [];
try {
  for (const mode of ["public", "private"]) {
    const name = `mlops-p1-inference-${mode}`;
    docker([
      "run",
      "--detach",
      "--name",
      name,
      "--label",
      "mlops.p1.test=true",
      "--network",
      "mlops_paas_network",
      "--mount",
      `type=bind,source=${path.join(root, "services/control-plane/scripts/p1_inference_worker.py")},target=/smoke/worker.py,readonly`,
      "-e",
      `PROJECT_ID=${fixture[mode].project}`,
      "-e",
      `MODEL_VERSION_ID=${fixture[mode].version}`,
      "mlops-paas-training-runner:latest",
      "python",
      "/smoke/worker.py",
    ]);
    runtimes.push(name);
  }
  const context = await browser.newContext();
  await context.addCookies([
    {
      name: "p1_cookie_probe",
      value: "must-not-reach-inference",
      domain: "localhost",
      path: "/",
    },
    {
      name: fixture.cookie,
      value: fixture.refresh,
      domain: "localhost",
      path: "/api/auth/",
      httpOnly: true,
      sameSite: "Lax",
    },
  ]);
  const page = await context.newPage();
  const gatewayRequests = [];
  let refreshRequests = 0;
  page.on("request", (request) => {
    if (request.url().startsWith("http://localhost:5002/"))
      gatewayRequests.push(request);
    if (request.url().includes("/auth/token/refresh/")) refreshRequests++;
  });
  await page.goto("http://localhost:5173/login");
  await page.waitForLoadState("networkidle");
  refreshRequests = 0;

  async function predict(url, token, timeout) {
    return page.evaluate(
      async ({ url, token, timeout }) => {
        const { setAuthSession, clearAuthSession, getAccessToken } =
          await import("/src/shared/api/authSession.ts");
        const { inferenceClient } =
          await import("/src/shared/api/inferenceClient.ts");
        if (token) setAuthSession({ access: token });
        else clearAuthSession();
        try {
          const result = await inferenceClient.post(
            url,
            { features: { feature: 1 } },
            timeout ? { timeout } : {},
          );
          return {
            status: result.status,
            success: result.data.success,
            authenticated: Boolean(getAccessToken()),
          };
        } catch (error) {
          return {
            status: error.response?.status ?? 0,
            code: error.code,
            authenticated: Boolean(getAccessToken()),
          };
        }
      },
      { url, token, timeout },
    );
  }

  assert.equal((await predict(fixture.public.url, null)).status, 200);
  assert.equal(
    (await predict(fixture.private.url, fixture.access)).status,
    200,
  );
  const refreshed = await predict(fixture.private.url, fixture.expired);
  assert.equal(refreshed.status, 200);
  assert.equal(refreshRequests, 1);
  const wrong = await predict(fixture.private.url, fixture.wrong_access);
  assert.equal(wrong.status, 403);
  assert.equal(wrong.authenticated, true);
  assert.equal(refreshRequests, 1);
  await page.route(fixture.private.url, async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 300));
    await route.abort();
  });
  const timeout = await predict(fixture.private.url, fixture.access, 100);
  assert.equal(timeout.code, "ECONNABORTED");
  assert.equal(timeout.authenticated, true);
  await page.unroute(fixture.private.url);
  for (const request of gatewayRequests)
    assert.equal((await request.allHeaders()).cookie, undefined);
  assert.ok(gatewayRequests.length >= 6);
  console.log(
    "PASS Chromium inference: public/private, actual expired-token refresh once, 403, timeout and no gateway cookies.",
  );
  await context.close();
} finally {
  await browser.close();
  for (const name of runtimes) docker(["rm", "--force", name]);
  docker([
    "exec",
    "control_plane",
    "python",
    "manage.py",
    "shell",
    "-c",
    "P1_FIXTURE_MODE='cleanup'; exec(open('scripts/p1_inference_fixture.py').read())",
  ]);
}
