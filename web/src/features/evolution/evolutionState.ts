import type {
  Build,
  ModelProject,
  ModelVersion,
} from "@/features/projects/types";
import type { VersionMetric } from "./types";
import { isDeployableBuild } from "@/features/deployments/deploymentEligibility";
import type { DriftMonitoringJob } from "@/features/monitoring/types";

export const EVOLUTION_TABS = [
  "details",
  "insights",
  "metrics",
  "history",
] as const;
export type EvolutionTab = (typeof EVOLUTION_TABS)[number];

export function evolutionParams(
  current: URLSearchParams,
  selection: { versionId?: string; tab?: string },
) {
  const next = new URLSearchParams(current);
  if (selection.versionId !== undefined)
    next.set("versionId", selection.versionId);
  if (selection.tab !== undefined) next.set("tab", selection.tab);
  return next;
}

export function chronologicalVersions(versions: ModelVersion[]) {
  return [...versions].sort(
    (a, b) =>
      a.registered_at.localeCompare(b.registered_at) ||
      a.id.localeCompare(b.id),
  );
}
export function runningVersionId(project?: ModelProject) {
  return project?.active_endpoint?.deployment_status === "succeeded"
    ? project.active_endpoint.version_id
    : undefined;
}
export function selectEvolutionVersion(
  versions: ModelVersion[],
  requested: string | null,
  running?: string,
) {
  if (requested !== null)
    return versions.find((version) => version.id === requested);
  return (
    versions.find((version) => version.id === running) ??
    chronologicalVersions(versions).at(-1)
  );
}
export function registeredVersionBuild(builds: Build[], version: ModelVersion) {
  return builds.find(
    (build) =>
      build.version_id === version.id &&
      isDeployableBuild(build, version.project_id),
  );
}
export function metricSeries(metrics: VersionMetric[]) {
  const groups = new Map<string, VersionMetric[]>();
  for (const metric of metrics) {
    if (metric.step === null || !Number.isFinite(metric.value)) continue;
    const points = groups.get(metric.name) ?? [];
    points.push(metric);
    groups.set(metric.name, points);
  }
  return [...groups.entries()].map(([name, points]) => ({
    name,
    points: points.sort(
      (a, b) =>
        a.step! - b.step! ||
        (a.timestamp ?? "").localeCompare(b.timestamp ?? ""),
    ),
  }));
}
export function versionDriftSummary(
  monitors: DriftMonitoringJob[],
  projectId: string,
  versionId: string,
) {
  return monitors
    .filter(
      (monitor) =>
        monitor.project_id === projectId && monitor.version_id === versionId,
    )
    .flatMap((monitor) =>
      monitor.runs
        .filter((run) => run.status === "completed")
        .map((run) => ({ monitor, run })),
    )
    .sort((a, b) =>
      (b.run.completed_at ?? b.run.created_at).localeCompare(
        a.run.completed_at ?? a.run.created_at,
      ),
    )[0];
}
export function comparisonRows(left: ModelVersion, right: ModelVersion) {
  const values = (version: ModelVersion): Record<string, unknown> => ({
    flavor: version.flavor,
    requirements: version.requirements_snapshot,
    ...Object.fromEntries(
      Object.entries(version.params_summary).map(([key, value]) => [
        `param.${key}`,
        value,
      ]),
    ),
    ...Object.fromEntries(
      Object.entries(version.metrics_summary).map(([key, value]) => [
        `metric.${key}`,
        value,
      ]),
    ),
    ...Object.fromEntries(
      Object.entries(version.supplemental_summaries ?? {}).flatMap(([kind, item]) =>
        item.value && typeof item.value === "object" && !Array.isArray(item.value)
          ? Object.entries(item.value).map(([key, value]) => [`supplemental.${kind}.${key}`, value])
          : [[`supplemental.${kind}`, item.value]],
      ),
    ),
    ...Object.fromEntries(
      version.artifacts.map((artifact) => [
        `artifact.${artifact.kind}.${artifact.name}`,
        {
          checksum: artifact.checksum,
          size_bytes: artifact.size_bytes,
        },
      ]),
    ),
  });
  const a = values(left),
    b = values(right);
  return [...new Set([...Object.keys(a), ...Object.keys(b)])].map((key) => ({
    key,
    left: a[key],
    right: b[key],
    delta:
      typeof a[key] === "number" &&
      typeof b[key] === "number" &&
      Number.isFinite(a[key]) &&
      Number.isFinite(b[key])
        ? b[key] - a[key]
        : null,
  }));
}
