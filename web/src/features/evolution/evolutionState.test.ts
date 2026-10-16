import {
  chronologicalVersions,
  comparisonRows,
  evolutionParams,
  EVOLUTION_TABS,
  metricSeries,
  registeredVersionBuild,
  runningVersionId,
  selectEvolutionVersion,
} from "@/features/evolution/evolutionState";
import type {
  ApiHealthStatus,
  Build,
  Deployment,
  ModelProject,
  ModelVersion,
} from "@/features/projects/types";
import type { VersionMetric } from "./types";
import { describe, expect, it } from "vitest";

describe("Evolution State & Lifecycle Utilities", () => {
  const createVersion = (
    id: string,
    time: string,
    overrides: Partial<ModelVersion> = {},
  ): ModelVersion => ({
    id,
    project_id: "project-1",
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

  const v1 = createVersion("1", "2026-01-01T00:00:00Z");
  const v2 = createVersion("2", "2026-01-02T00:00:00Z");

  it("should sort versions chronologically", () => {
    expect(chronologicalVersions([v2, v1])).toEqual([v1, v2]);
  });

  it("should select version by requested ID, running fallback, or latest", () => {
    expect(selectEvolutionVersion([v2, v1], null, "1")).toBe(v1);
    expect(selectEvolutionVersion([v1, v2], null)).toBe(v2);
    expect(selectEvolutionVersion([v1, v2], "missing", "1")).toBeUndefined();
    expect(selectEvolutionVersion([v1, v2], "", "1")).toBeUndefined();
    expect(selectEvolutionVersion([], null)).toBeUndefined();
    expect(selectEvolutionVersion([v1, v2], "2", "1")).toBe(v2);
  });

  it("should resolve running version ID only if endpoint deployment succeeded", () => {
    const project = (
      health: ApiHealthStatus,
      status: Deployment["status"] = "succeeded",
    ): ModelProject =>
      ({
        id: "project-1",
        name: "Test",
        active_endpoint: {
          version_id: "1",
          deployment_status: status,
          health_status: health,
        },
      }) as unknown as ModelProject;

    for (const health of [
      "healthy",
      "unhealthy",
      "unknown",
    ] as ApiHealthStatus[]) {
      expect(runningVersionId(project(health))).toBe("1");
    }

    expect(runningVersionId(project("healthy", "stopped"))).toBeUndefined();
    expect(runningVersionId({} as unknown as ModelProject)).toBeUndefined();
  });

  it("should identify registered deployable build for a version", () => {
    const build = {
      id: "build-1",
      project_id: "project-1",
      version_id: "1",
      status: "ready",
      registration_status: "registered",
      deletion_state: "active",
      image_uri: "img:1",
      created_at: "2026-01-01T00:00:00Z",
    } as unknown as Build;

    expect(registeredVersionBuild([build], v1)).toBe(build);

    const invalidOverrides: Partial<Build>[] = [
      { project_id: "other" },
      { version_id: "2" },
      { status: "failed" },
      { registration_status: "unregistered" },
      { deletion_state: "deleting" },
      { deletion_state: "delete_failed" },
    ];

    for (const override of invalidOverrides) {
      expect(
        registeredVersionBuild([
          { ...build, ...override } as unknown as Build,
        ], v1),
      ).toBeUndefined();
    }
  });

  it("should extract ordered metric series ignoring null steps and non-finite values", () => {
    const metrics = [
      { name: "accuracy", step: 2, value: 0.9, timestamp: null },
      { name: "accuracy", step: 1, value: 0.8, timestamp: null },
      { name: "summary", step: null, value: 1, timestamp: null },
      { name: "invalid", step: 1, value: Infinity, timestamp: null },
    ];

    const series = metricSeries(metrics as unknown as VersionMetric[]);
    expect(series.length).toBe(1);
    expect(series[0].points.map((p) => p.value)).toEqual([0.8, 0.9]);
    expect(metricSeries([])).toEqual([]);
  });

  it("should calculate delta and comparison rows between two versions", () => {
    const left: ModelVersion = {
      ...v1,
      metrics_summary: { score: 0.4 },
      params_summary: { depth: 3 },
      artifacts: [
        {
          id: "art-1",
          kind: "reference_data",
          name: "ref.csv",
          uri: "s3://bucket/ref.csv",
          checksum: "a",
          size_bytes: 10,
          content_type: "text/csv",
          metadata: {},
          created_at: "2026-01-01T00:00:00Z",
        },
      ],
    };

    const right: ModelVersion = {
      ...v2,
      metrics_summary: { score: 0.9, loss: 0.1 },
      artifacts: [
        {
          id: "art-2",
          kind: "reference_data",
          name: "ref.csv",
          uri: "s3://bucket/ref.csv",
          checksum: "b",
          size_bytes: 20,
          content_type: "text/csv",
          metadata: {},
          created_at: "2026-01-01T00:00:00Z",
        },
      ],
    };

    const comparison = comparisonRows(left, right);
    expect(comparison.find((r) => r.key === "metric.score")?.delta).toBeCloseTo(0.5);
    expect(comparison.find((r) => r.key === "metric.loss")?.left).toBeUndefined();
    expect(comparison.find((r) => r.key === "param.depth")?.right).toBeUndefined();
    expect(comparison.find((r) => r.key === "requirements")?.left).toBe(
      v1.requirements_snapshot,
    );
    const artifactRight = comparison.find((r) => r.key.startsWith("artifact."))
      ?.right as { checksum?: string } | undefined;
    expect(artifactRight?.checksum).toBe("b");
  });

  it("should preserve query parameters with evolutionParams", () => {
    const routeParams = new URLSearchParams("versionId=1&tab=metrics&other=keep");

    expect(evolutionParams(routeParams, { versionId: "2" }).get("tab")).toBe("metrics");
    expect(evolutionParams(routeParams, { tab: "history" }).get("versionId")).toBe("1");
    expect(evolutionParams(routeParams, { tab: "history" }).get("other")).toBe("keep");
    expect(routeParams.get("versionId")).toBe("1");
  });

  it("should define standard EVOLUTION_TABS", () => {
    expect(EVOLUTION_TABS).toEqual([
      "information",
      "monitoring",
      "attributes",
      "code",
      "data",
    ]);
  });
});
