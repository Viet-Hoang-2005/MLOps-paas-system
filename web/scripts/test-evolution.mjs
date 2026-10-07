import assert from "node:assert/strict";
import { readFileSync, existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import ts from "typescript";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router-dom";
import i18next from "i18next";
import { I18nextProvider } from "react-i18next";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { parseResource, validateResourcePair } from "./i18n-resources.mjs";

// Transpile real modules in memory using the existing TypeScript/Node tooling.
const modules = new Map();
function moduleURL(file) {
  const key = file.href;
  if (modules.has(key)) return modules.get(key);
  let output = ts.transpileModule(readFileSync(file, "utf8"), {
    compilerOptions: { module: ts.ModuleKind.ES2022, jsx: ts.JsxEmit.ReactJSX },
  }).outputText;
  for (const match of [...output.matchAll(/from\s+(["'])([^"']+)\1/g)]) {
    const specifier = match[2];
    let target;
    if (specifier.startsWith("@/") || specifier.startsWith("./")) {
      const base = specifier.startsWith("@/")
        ? new URL(`../src/${specifier.slice(2)}`, import.meta.url)
        : new URL(specifier, file);
      target = moduleURL(
        new URL(
          base.href +
            (existsSync(fileURLToPath(new URL(base.href + ".tsx")))
              ? ".tsx"
              : ".ts"),
        ),
      );
    } else target = import.meta.resolve(specifier);
    output = output.replace(match[0], `from ${JSON.stringify(target)}`);
  }
  const url = `data:text/javascript;base64,${Buffer.from(output).toString("base64")}`;
  modules.set(key, url);
  return url;
}
const load = (path) =>
  import(moduleURL(new URL(`../src/${path}`, import.meta.url)));
const state = await load("features/evolution/evolutionState.ts");
const { runDeploymentPath } = await load("features/deployments/navigation.ts");
let checks = 0;
function check(run) {
  run();
  checks += 1;
}
const version = (id, time, overrides = {}) => ({
  id,
  project_id: "project",
  version: id,
  registered_at: time,
  source_job_id: null,
  flavor: "xgboost",
  requirements_snapshot: "numpy>=1.24\npandas>=2.0",
  deployability: "deployable",
  deployability_reason: "",
  stage: "none",
  artifacts: [],
  metrics: [],
  events: [],
  metrics_summary: {},
  params_summary: {},
  insights_summary: {},
  ...overrides,
});
const a = version("1", "2026-01-01T00:00:00Z");
const b = version("2", "2026-01-02T00:00:00Z");
check(() => assert.deepEqual(state.chronologicalVersions([b, a]), [a, b]));
check(() => assert.equal(state.selectEvolutionVersion([b, a], null, "1"), a));
check(() => assert.equal(state.selectEvolutionVersion([a, b], null), b));
check(() =>
  assert.equal(state.selectEvolutionVersion([a, b], "missing", "1"), undefined),
);
check(() =>
  assert.equal(state.selectEvolutionVersion([a, b], "", "1"), undefined),
);
check(() => assert.equal(state.selectEvolutionVersion([], null), undefined));
check(() => assert.equal(state.selectEvolutionVersion([a, b], "2", "1"), b));
const project = (health) => ({
  active_endpoint: {
    version_id: "1",
    deployment_status: "succeeded",
    health_status: health,
  },
});
for (const health of ["healthy", "unhealthy", "unknown"])
  check(() => assert.equal(state.runningVersionId(project(health)), "1"));
check(() =>
  assert.equal(
    state.runningVersionId({
      active_endpoint: {
        ...project("healthy").active_endpoint,
        deployment_status: "stopped",
      },
    }),
    undefined,
  ),
);
check(() => assert.equal(state.runningVersionId({}), undefined));
const build = {
  id: "build",
  project_id: "project",
  version_id: "1",
  status: "ready",
  registration_status: "registered",
  deletion_state: "active",
};
check(() => assert.equal(state.registeredVersionBuild([build], a), build));
check(() =>
  assert.equal(
    runDeploymentPath("project", "build"),
    "/dashboard/deployment/run/project/build",
  ),
);
for (const override of [
  { project_id: "other" },
  { version_id: "2" },
  { status: "failed" },
  { registration_status: "unregistered" },
  { deletion_state: "deleting" },
  { deletion_state: "delete_failed" },
])
  check(() =>
    assert.equal(
      state.registeredVersionBuild([{ ...build, ...override }], a),
      undefined,
    ),
  );
const metrics = [
  { name: "accuracy", step: 2, value: 0.9, timestamp: null },
  { name: "accuracy", step: 1, value: 0, timestamp: null },
  { name: "summary", step: null, value: 1, timestamp: null },
  { name: "invalid", step: 1, value: Infinity, timestamp: null },
];
check(() =>
  assert.deepEqual(
    state.metricSeries(metrics)[0].points.map((point) => point.value),
    [0, 0.9],
  ),
);
check(() => assert.equal(state.metricSeries(metrics).length, 1));
check(() => assert.equal(metrics[0].step, 2));
check(() => assert.deepEqual(state.metricSeries([]), []));
const left = {
  ...a,
  metrics_summary: { score: 0 },
  params_summary: { depth: 3 },
  artifacts: [
    {
      kind: "reference_data",
      name: "reference.csv",
      checksum: "a",
      size_bytes: 10,
    },
  ],
};
const right = {
  ...b,
  metrics_summary: { score: 0.5, loss: 0 },
  artifacts: [
    {
      kind: "reference_data",
      name: "reference.csv",
      checksum: "b",
      size_bytes: 20,
    },
  ],
};
const comparison = state.comparisonRows(left, right);
check(() =>
  assert.equal(comparison.find((row) => row.key === "metric.score").delta, 0.5),
);
check(() =>
  assert.equal(
    comparison.find((row) => row.key === "metric.loss").left,
    undefined,
  ),
);
check(() =>
  assert.equal(
    comparison.find((row) => row.key === "param.depth").right,
    undefined,
  ),
);
check(() =>
  assert.equal(
    comparison.find((row) => row.key === "requirements").left,
    a.requirements_snapshot,
  ),
);
check(() =>
  assert.equal(
    comparison.find((row) => row.key.startsWith("artifact.")).right.checksum,
    "b",
  ),
);
const monitor = (id, project_id, version_id, overrides = {}) => ({
  id,
  project_id,
  version_id,
  runs: [
    {
      id,
      status: "completed",
      created_at: "2026-01-02",
      completed_at: null,
      drift_score: 0,
      has_drift: false,
      ...overrides,
    },
  ],
});
const monitors = [
  monitor("old", "project", "2"),
  monitor("other", "tenant", "1"),
  monitor("current", "project", "1"),
  monitor("pending", "project", "1", {
    status: "pending",
    created_at: "2026-02-01",
  }),
];
check(() =>
  assert.equal(
    state.versionDriftSummary(monitors, "project", "1").monitor.id,
    "current",
  ),
);
check(() =>
  assert.equal(
    state.versionDriftSummary(monitors, "project", "missing"),
    undefined,
  ),
);
check(() =>
  assert.deepEqual(state.EVOLUTION_TABS, [
    "details",
    "insights",
    "metrics",
    "history",
  ]),
);

const readResource = (path) =>
  parseResource(
    readFileSync(new URL(`../src/${path}`, import.meta.url), "utf8"),
  ).resource;
const en = readResource("features/evolution/i18n/en.ts"),
  vi = readResource("features/evolution/i18n/vi.ts");
check(() => assert.deepEqual(validateResourcePair(en, vi, "evolution"), []));
const { VersionLineage } = await load(
  "features/evolution/components/VersionLineage.tsx",
);
const routeParams = new URLSearchParams("versionId=1&tab=metrics&other=keep");
check(() =>
  assert.equal(
    state.evolutionParams(routeParams, { versionId: "2" }).get("tab"),
    "metrics",
  ),
);
check(() =>
  assert.equal(
    state.evolutionParams(routeParams, { tab: "history" }).get("versionId"),
    "1",
  ),
);
check(() =>
  assert.equal(
    state.evolutionParams(routeParams, { tab: "history" }).get("other"),
    "keep",
  ),
);
check(() => assert.equal(routeParams.get("versionId"), "1"));
check(() =>
  assert.equal(
    state.selectEvolutionVersion(
      [a, b],
      new URLSearchParams(
        state.evolutionParams(routeParams, { versionId: "2" }).toString(),
      ).get("versionId"),
    ),
    b,
  ),
);
const { VersionDetails } = await load(
  "features/evolution/components/VersionDetails.tsx",
);
const { VersionInsights } = await load(
  "features/evolution/components/VersionInsights.tsx",
);
const { VersionMetrics } = await load(
  "features/evolution/components/VersionMetrics.tsx",
);
const { Chart } = await load("shared/components/Chart.tsx");
const { VersionHistory } = await load(
  "features/evolution/components/VersionHistory.tsx",
);
const { VersionDriftSummary } = await load(
  "features/evolution/components/VersionDriftSummary.tsx",
);
for (const language of ["en", "vi"]) {
  const instance = i18next.createInstance();
  await instance.init({
    lng: language,
    fallbackLng: "en",
    resources: { en: { evolution: en }, vi: { evolution: vi } },
    interpolation: { escapeValue: false },
  });
  const queryClient = new QueryClient();
  const render = (component, props) =>
    renderToStaticMarkup(
      React.createElement(
        QueryClientProvider,
        { client: queryClient },
        React.createElement(
          I18nextProvider,
          { i18n: instance },
          React.createElement(
            MemoryRouter,
            null,
            React.createElement(component, props),
          ),
        ),
      ),
    );
  check(() =>
    assert.doesNotMatch(
      render(Chart, {
        data: [
          { timestamp: 0, value: -1 },
          { timestamp: 1, value: -1 },
        ],
        allowNegative: true,
      }),
      /NaN|Infinity/,
    ),
  );
  check(() =>
    assert.match(
      render(Chart, {
        data: [
          { timestamp: 0, value: -2 },
          { timestamp: 1, value: -1 },
        ],
        allowNegative: true,
      }),
      />-2/,
    ),
  );
  check(() =>
    assert.match(
      render(VersionLineage, {
        versions: [b, a],
        selectedId: "1",
        runningId: "1",
        onSelect() {},
      }),
      /aria-current="true"/,
    ),
  );
  check(() =>
    assert.match(
      render(VersionLineage, {
        versions: [b, a],
        runningId: "1",
        onSelect() {},
      }),
      new RegExp(language === "en" ? "Running" : "Đang chạy"),
    ),
  );
  check(() =>
    assert.match(
      render(VersionDetails, {
        version: { ...a, source_job_id: "training" },
        build,
      }),
      /training\/jobs\/training\/overview/,
    ),
  );
  check(() =>
    assert.match(render(VersionDetails, { version: a }), /numpy&gt;=1.24/),
  );
  check(() =>
    assert.match(
      render(VersionMetrics, { version: a }),
      new RegExp(language === "en" ? "No metrics recorded" : "Chưa có metric"),
    ),
  );
  check(() =>
    assert.match(
      render(VersionMetrics, {
        version: { ...a, metrics_summary: { accuracy: 0 } },
      }),
      /accuracy/,
    ),
  );
  check(() =>
    assert.match(
      render(VersionInsights, { version: a }),
      new RegExp(language === "en" ? "No model insights" : "Chưa có phân tích"),
    ),
  );
  check(() =>
    assert.doesNotMatch(
      render(VersionInsights, {
        version: {
          ...a,
          insights_summary: { items: [{ name: "feature", value: 0 }] },
        },
      }),
      /NaN|Infinity/,
    ),
  );
  check(() =>
    assert.match(
      render(VersionHistory, { events: [] }),
      new RegExp(language === "en" ? "No lifecycle events" : "Chưa có sự kiện"),
    ),
  );
  check(() =>
    assert.match(
      render(VersionHistory, {
        events: [
          {
            id: "event",
            event_type: "registered",
            created_at: a.registered_at,
            from_state: "",
            to_state: "",
            metadata: {},
          },
        ],
      }),
      new RegExp(language === "en" ? "Model registered" : "Đã đăng ký mô hình"),
    ),
  );
  check(() =>
    assert.match(
      render(VersionDriftSummary, {
        monitors,
        projectId: "project",
        versionId: "1",
        loading: false,
        error: null,
        retry() {},
      }),
      /monitorId=current/,
    ),
  );
}
console.log(
  `Evolution lifecycle, comparison, resource parity and SSR: ${checks} checks passed`,
);
