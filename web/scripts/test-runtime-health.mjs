import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import ts from "typescript";

const compiled = ts.transpileModule(
  readFileSync(
    new URL("../src/features/overview/runtimeHealth.ts", import.meta.url),
    "utf8",
  ),
  { compilerOptions: { module: ts.ModuleKind.ES2022 } },
).outputText;
const { currentApiHealth } = await import(
  `data:text/javascript;base64,${Buffer.from(compiled).toString("base64")}`
);
const now = Date.now();
const endpoint = {
  deployment_status: "succeeded",
  health_status: "healthy",
  last_checked_at: new Date(now).toISOString(),
};
assert.equal(currentApiHealth(endpoint, false, now), "healthy");
assert.equal(
  currentApiHealth({ ...endpoint, health_status: "unhealthy" }, false, now),
  "unhealthy",
);
assert.equal(
  currentApiHealth({ ...endpoint, health_status: "unknown" }, false, now),
  "unknown",
);
assert.equal(currentApiHealth(endpoint, true, now), "unknown");
assert.equal(currentApiHealth(endpoint, false, now + 46000), "unknown");
assert.equal(
  currentApiHealth({ ...endpoint, last_checked_at: null }, false, now),
  "unknown",
);
assert.equal(
  currentApiHealth({ ...endpoint, last_checked_at: "invalid" }, false, now),
  "unknown",
);
assert.equal(
  currentApiHealth(
    { ...endpoint, last_checked_at: new Date(now + 6000).toISOString() },
    false,
    now,
  ),
  "unknown",
);
assert.equal(
  currentApiHealth({ ...endpoint, deployment_status: "stopped" }, false, now),
  "unknown",
);
assert.equal(currentApiHealth(null, false, now), "unknown");
const runPage = readFileSync(
  new URL(
    "../src/features/deployments/pages/RunDeploymentPage.tsx",
    import.meta.url,
  ),
  "utf8",
);
assert.ok(
  /"succeeded",\s*"failed",\s*"stopped",\s*"unconfirmed"/.test(runPage),
);
assert.ok(!runPage.includes('deployment.status === "healthy"'));
const statusLine = readFileSync(
  new URL(
    "../src/features/overview/components/ModelStatusLine.tsx",
    import.meta.url,
  ),
  "utf8",
);
assert.ok(statusLine.includes("registration_status"));
assert.ok(statusLine.includes("currentApiHealth"));
console.log("Runtime health: 14 cases passed");
