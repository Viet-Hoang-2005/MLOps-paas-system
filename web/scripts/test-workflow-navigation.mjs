import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import ts from "typescript";

const source = readFileSync(
  new URL("../src/features/projects/navigation.ts", import.meta.url),
  "utf8",
);
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.ES2022 },
}).outputText;
const { projectSelectionPath } = await import(
  `data:text/javascript;base64,${Buffer.from(compiled).toString("base64")}`
);
let cases = 0;
for (const section of [
  "overview",
  "deployment",
  "monitoring",
  "training",
  "evolution",
]) {
  assert.equal(
    projectSelectionPath(`/dashboard/projects/old/${section}`, "new"),
    `/dashboard/projects/new/${section}`,
  );
  cases++;
  assert.equal(
    projectSelectionPath(`/dashboard/${section}`, "new"),
    `/dashboard/projects/new/${section}`,
  );
  cases++;
}
for (const path of [
  "/dashboard/projects/old/edit",
  "/dashboard/projects/new",
  "/dashboard/projects/old/monitoring/report/run-id",
  "/dashboard/deployments/new",
  "/dashboard/training/jobs/job-id/config",
  "/dashboard/settings/profile",
  "/dashboard/api-tokens",
  "/dashboard/notifications",
]) {
  assert.equal(
    projectSelectionPath(path, "new"),
    "/dashboard/projects/new/overview",
  );
  cases++;
}
console.log(`Workflow navigation: ${cases} cases passed`);
