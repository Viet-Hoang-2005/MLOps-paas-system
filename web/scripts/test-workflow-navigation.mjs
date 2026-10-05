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
const eligibilitySource = readFileSync(
  new URL(
    "../src/features/deployments/deploymentEligibility.ts",
    import.meta.url,
  ),
  "utf8",
);
const eligibilityCompiled = ts.transpileModule(eligibilitySource, {
  compilerOptions: { module: ts.ModuleKind.ES2022 },
}).outputText;
const { isDeployableBuild, deploymentMatchesBuild } = await import(
  `data:text/javascript;base64,${Buffer.from(eligibilityCompiled).toString("base64")}`
);
const registeredBuild = {
  id: "build-a",
  project_id: "project-a",
  version_id: "version-a",
  status: "ready",
  deletion_state: "active",
  registration_status: "registered",
};
assert.equal(isDeployableBuild(registeredBuild, "project-a"), true);
assert.equal(isDeployableBuild(registeredBuild, "project-b"), false);
assert.equal(
  isDeployableBuild(
    { ...registeredBuild, registration_status: "unregistered" },
    "project-a",
  ),
  false,
);
assert.equal(
  isDeployableBuild({ ...registeredBuild, version_id: null }, "project-a"),
  false,
);
assert.equal(
  deploymentMatchesBuild(
    { build_id: "build-a", version_id: "version-a" },
    registeredBuild,
  ),
  true,
);
assert.equal(
  deploymentMatchesBuild(
    { build_id: "build-b", version_id: "version-a" },
    registeredBuild,
  ),
  false,
);
assert.equal(
  deploymentMatchesBuild(
    { build_id: "build-a", version_id: "version-b" },
    registeredBuild,
  ),
  false,
);
cases += 7;

// Run is bound to its route's registered Build, not a version picker.
const runSource = readFileSync(
  new URL(
    "../src/features/deployments/pages/RunDeploymentPage.tsx",
    import.meta.url,
  ),
  "utf8",
);
const runFile = ts.createSourceFile(
  "RunDeploymentPage.tsx",
  runSource,
  ts.ScriptTarget.Latest,
  true,
  ts.ScriptKind.TSX,
);
let selectors = 0;
function visit(node) {
  if (
    (ts.isJsxOpeningElement(node) || ts.isJsxSelfClosingElement(node)) &&
    ["Select", "select"].includes(node.tagName.getText(runFile))
  )
    selectors++;
  ts.forEachChild(node, visit);
}
visit(runFile);
assert.equal(
  selectors,
  0,
  "Run deployment must not allow selecting a different Build/version",
);
cases++;
console.log(
  `Workflow navigation and deployment eligibility: ${cases} cases passed`,
);
