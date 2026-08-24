import { useState } from "react";
import { AlertTriangle, GitCompare, X } from "lucide-react";
import { Button } from "@/shared/components/Button";
import type {
  RegistryFamily,
  RegistryVersion,
  RegistryVersionCompareResponse,
} from "@/features/registry/types";
import { compareRegistryVersions } from "@/features/registry/api/registryApi";
import { getApiErrorMessage } from "@/shared/api/errors";
import { formatVersion } from "@/shared/lib/formatters";
import { toast } from "@/shared/components/toastStore";
import { useTranslation } from "react-i18next";

interface Props {
  family: RegistryFamily;
  versions: RegistryVersion[];
  onClose: () => void;
}

const classNames = (...classes: (string | undefined | null | false)[]) =>
  classes.filter(Boolean).join(" ");

function formatValue(value: unknown): string {
  if (typeof value === "number")
    return Number.isInteger(value) ? value.toString() : value.toFixed(4);
  if (value === null || value === undefined || value === "") return "-";
  if (typeof value === "object") {
    const compact = JSON.stringify(value);
    return compact.length > 96 ? `${compact.slice(0, 95)}…` : compact;
  }
  const text = String(value);
  return text.length > 96 ? `${text.slice(0, 95)}…` : text;
}

function formatDelta(value: number | null): string {
  if (value === null || value === undefined) return "-";
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(4)}`;
}

function winnerClass(winner: string) {
  if (winner === "right") return "border-info-border bg-info-subtle text-color-info";
  if (winner === "left")
    return "border-success-border bg-success-subtle text-color-success";
  if (winner === "tie") return "border-border bg-surface-muted text-color-foreground";
  return "border-border bg-surface-muted text-color-foreground-subtle";
}

function DeployabilityPill({ status }: { status?: string }) {
  const { t } = useTranslation("registry");
  const cls =
    status === "deployable"
      ? "border-success-border bg-success-subtle text-color-success"
      : status === "track_only"
        ? "border-warning-border bg-warning-subtle text-color-warning"
        : status === "invalid"
          ? "border-danger-border bg-danger-subtle text-color-danger"
          : "border-border bg-surface-muted text-color-foreground";
  return (
    <span
      className={classNames(
        "rounded-full border px-2 py-0.5 text-style-caption-strong uppercase",
        cls,
      )}
    >
      {status || t("comparison.unknown")}
    </span>
  );
}

export function VersionComparisonModal({ family, versions, onClose }: Props) {
  const { t } = useTranslation("registry");
  const [leftId, setLeftId] = useState<string>(versions[0]?.id ?? "");
  const [rightId, setRightId] = useState<string>(
    versions[1]?.id || versions[0]?.id || "",
  );
  const [loading, setLoading] = useState(false);
  const [comparison, setComparison] =
    useState<RegistryVersionCompareResponse | null>(null);

  const runCompare = async () => {
    if (!leftId || !rightId || leftId === rightId) {
      toast.error(t("comparison.chooseDifferent"));
      return;
    }
    setLoading(true);
    try {
      const data = await compareRegistryVersions(family.id, leftId, rightId);
      setComparison(data);
    } catch (error) {
      toast.error(getApiErrorMessage(error, t("comparison.loadFailed")));
    } finally {
      setLoading(false);
    }
  };

  if (versions.length < 2) {
    return (
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-overlay p-4 backdrop-blur-sm">
        <div className="bg-surface rounded-overlay shadow-xl w-full max-w-md overflow-hidden text-center p-8">
          <div className="mx-auto bg-muted rounded-full w-16 h-16 flex items-center justify-center mb-4">
            <GitCompare className="h-8 w-8 text-color-muted-foreground" />
          </div>
          <h3 className="text-style-section-title font-bold text-color-foreground mb-2">
            {t("comparison.insufficientTitle")}
          </h3>
          <p className="text-style-body text-color-muted-foreground mb-6">
            {t("comparison.insufficientDescription")}
          </p>
          <Button
            variant="primary"
            onClick={onClose}
            className="w-full justify-center"
          >
            {t("comparison.close")}
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-overlay p-4 backdrop-blur-sm">
      <div className="bg-surface rounded-overlay shadow-xl w-full max-w-6xl max-h-[90vh] flex flex-col overflow-hidden">
        <div className="flex justify-between items-center p-6 border-b border-border">
          <div className="flex items-center gap-3">
            <div className="rounded-surface bg-info-subtle p-2 text-color-info">
              <GitCompare className="h-5 w-5" />
            </div>
            <div>
              <h2 className="text-style-section-title font-bold text-color-foreground">
                {t("comparison.title")}
              </h2>
              <p className="text-style-body text-color-muted-foreground">
                {t("comparison.family", {
                  name: family.display_name || family.name,
                })}
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="text-color-muted-foreground hover:text-color-muted-foreground transition-colors p-2 rounded-full hover:bg-muted"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-6 bg-muted/50">
          <div className="grid md:grid-cols-[1fr_1fr_auto] gap-4 mb-6 rounded-surface border border-border bg-surface p-4 shadow-sm">
            <select
              className="w-full rounded-control border border-border bg-surface px-3 py-2 text-style-body-strong shadow-sm focus:ring-2 focus:ring-ring"
              value={leftId}
              onChange={(event) => setLeftId(event.target.value)}
            >
              {versions.map((version) => (
                <option key={version.id} value={version.id}>
                  {t("comparison.leftOption", {
                    version: formatVersion(version.version),
                  })}{" "}
                  {version.stage === "production"
                    ? t("comparison.productionSuffix")
                    : ""}
                </option>
              ))}
            </select>
            <select
              className="w-full rounded-control border border-border bg-surface px-3 py-2 text-style-body-strong shadow-sm focus:ring-2 focus:ring-ring"
              value={rightId}
              onChange={(event) => setRightId(event.target.value)}
            >
              {versions.map((version) => (
                <option key={version.id} value={version.id}>
                  {t("comparison.rightOption", {
                    version: formatVersion(version.version),
                  })}{" "}
                  {version.stage === "production"
                    ? t("comparison.productionSuffix")
                    : ""}
                </option>
              ))}
            </select>
            <Button
              variant="primary"
              onClick={() => void runCompare()}
              disabled={loading}
            >
              {loading ? t("comparison.comparing") : t("comparison.compare")}
            </Button>
          </div>

          <p className="mb-6 text-style-body text-color-muted-foreground">
            {t("comparison.description")}
          </p>

          {comparison ? (
            <div className="space-y-6">
              <section className="rounded-surface border border-border bg-surface p-5 shadow-sm">
                <div className="flex flex-col md:flex-row md:items-start md:justify-between gap-3">
                  <div>
                    <h3 className="text-style-heading font-bold text-color-foreground">
                      {t("comparison.recommendation")}
                    </h3>
                    <p className="mt-1 text-style-body text-color-muted-foreground">
                      {comparison.recommendation.reason}
                    </p>
                  </div>
                  <span className="rounded-full border border-border bg-muted px-3 py-1 text-style-caption-strong uppercase text-color-foreground">
                    {t("comparison.winnerSummary", {
                      winner: comparison.recommendation.winner,
                      confidence: comparison.recommendation.confidence,
                    })}
                  </span>
                </div>
                {comparison.recommendation.warnings.length > 0 && (
                  <div className="mt-4 space-y-2">
                    {comparison.recommendation.warnings.map((warning) => (
                      <div
                        key={warning}
                        className="flex items-start gap-2 rounded-surface border border-warning-border bg-warning-subtle p-3 text-style-body text-color-warning"
                      >
                        <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
                        {warning}
                      </div>
                    ))}
                  </div>
                )}
              </section>

              <section className="grid md:grid-cols-2 gap-4">
                {[comparison.left, comparison.right].map((version, index) => (
                  <div
                    key={version.id}
                    className="rounded-surface border border-border bg-surface p-5 shadow-sm"
                  >
                    <p className="text-style-overline uppercase text-color-muted-foreground">
                      {index === 0
                        ? t("comparison.left")
                        : t("comparison.right")}
                    </p>
                    <h3 className="mt-1 text-style-section-title font-bold text-color-foreground">
                      {formatVersion(version.version)}
                    </h3>
                    <div className="mt-3 flex flex-wrap gap-2">
                      <span className="rounded-full bg-muted px-2 py-0.5 text-style-caption-strong uppercase text-color-foreground">
                        {version.stage}
                      </span>
                      <DeployabilityPill
                        status={version.deployability_status}
                      />
                      <span className="rounded-full border border-info-border bg-info-subtle px-2 py-0.5 text-style-caption-strong uppercase text-color-info">
                        {version.tracking_status || t("comparison.notSynced")}
                      </span>
                    </div>
                  </div>
                ))}
              </section>

              <section className="rounded-surface border border-border bg-surface shadow-sm overflow-hidden">
                <div className="border-b border-border px-5 py-3">
                  <h3 className="text-style-overline uppercase text-color-foreground">
                    {t("comparison.metricsDiff")}
                  </h3>
                </div>
                <div className="overflow-x-auto">
                  <table className="min-w-full text-style-body">
                    <thead className="bg-muted text-style-caption uppercase text-color-muted-foreground">
                      <tr>
                        <th className="px-4 py-2 text-left">{t("comparison.metric")}</th>
                        <th className="px-4 py-2 text-right">{t("comparison.left")}</th>
                        <th className="px-4 py-2 text-right">{t("comparison.right")}</th>
                        <th className="px-4 py-2 text-right">{t("comparison.delta")}</th>
                        <th className="px-4 py-2 text-left">{t("comparison.winner")}</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-border">
                      {comparison.metrics_diff.length === 0 ? (
                        <tr>
                          <td
                            colSpan={5}
                            className="px-4 py-6 text-center text-color-muted-foreground"
                          >
                            {t("comparison.noMetrics")}
                          </td>
                        </tr>
                      ) : (
                        comparison.metrics_diff.map((metric) => (
                          <tr key={metric.name}>
                            <td className="px-4 py-2 font-semibold text-color-foreground">
                              {metric.name}
                            </td>
                            <td className="px-4 py-2 text-right font-mono">
                              {formatValue(metric.left)}
                            </td>
                            <td className="px-4 py-2 text-right font-mono">
                              {formatValue(metric.right)}
                            </td>
                            <td className="px-4 py-2 text-right font-mono">
                              {formatDelta(metric.delta)}
                            </td>
                            <td className="px-4 py-2">
                              <span
                                className={classNames(
                                  "rounded-full border px-2 py-0.5 text-style-caption-strong uppercase",
                                  winnerClass(metric.winner),
                                )}
                              >
                                {metric.winner}
                              </span>
                            </td>
                          </tr>
                        ))
                      )}
                    </tbody>
                  </table>
                </div>
              </section>

              <section className="grid xl:grid-cols-2 gap-6">
                <div className="rounded-surface border border-border bg-surface shadow-sm overflow-hidden">
                  <div className="border-b border-border px-5 py-3">
                    <h3 className="text-style-overline uppercase text-color-foreground">
                      {t("comparison.paramsDiff")}
                    </h3>
                  </div>
                  <div className="max-h-72 overflow-auto">
                    <table className="min-w-full text-style-body">
                      <tbody className="divide-y divide-border">
                        {comparison.params_diff.length === 0 ? (
                          <tr>
                            <td className="px-4 py-6 text-center text-color-muted-foreground">
                              {t("comparison.noParams")}
                            </td>
                          </tr>
                        ) : (
                          comparison.params_diff.map((param) => (
                            <tr
                              key={param.name}
                              className={param.changed ? "bg-warning-subtle" : ""}
                            >
                              <td className="px-4 py-2 font-semibold text-color-foreground">
                                {param.name}
                              </td>
                              <td className="px-4 py-2 font-mono text-color-muted-foreground">
                                {formatValue(param.left)}
                              </td>
                              <td className="px-4 py-2 font-mono text-color-foreground">
                                {formatValue(param.right)}
                              </td>
                            </tr>
                          ))
                        )}
                      </tbody>
                    </table>
                  </div>
                </div>

                <div className="rounded-surface border border-border bg-surface p-5 shadow-sm">
                  <h3 className="text-style-overline uppercase text-color-foreground">
                    {t("comparison.deployability")}
                  </h3>
                  <div className="mt-4 grid gap-3 text-style-body">
                    <div className="flex items-center justify-between gap-3">
                      <span className="font-medium text-color-muted-foreground">
                        {t("comparison.left")}
                      </span>
                      <DeployabilityPill
                        status={comparison.deployability_diff.left.status}
                      />
                    </div>
                    <p className="text-style-caption text-color-muted-foreground">
                      {comparison.deployability_diff.left.reason || "-"}
                    </p>
                    <div className="flex items-center justify-between gap-3 border-t border-border pt-3">
                      <span className="font-medium text-color-muted-foreground">
                        {t("comparison.right")}
                      </span>
                      <DeployabilityPill
                        status={comparison.deployability_diff.right.status}
                      />
                    </div>
                    <p className="text-style-caption text-color-muted-foreground">
                      {comparison.deployability_diff.right.reason || "-"}
                    </p>
                    <div className="border-t border-border pt-3 text-style-caption text-color-muted-foreground">
                      <p>{t("comparison.stageDeployment", {
                        side: t("comparison.left"),
                        stage: comparison.deployment_diff.left_stage,
                        deployed: comparison.deployment_diff.left_deployed
                          ? t("comparison.yes")
                          : t("comparison.no"),
                      })}</p>
                      <p>{t("comparison.stageDeployment", {
                        side: t("comparison.right"),
                        stage: comparison.deployment_diff.right_stage,
                        deployed: comparison.deployment_diff.right_deployed
                          ? t("comparison.yes")
                          : t("comparison.no"),
                      })}</p>
                    </div>
                  </div>
                </div>
              </section>

              <section className="rounded-surface border border-border bg-surface p-5 shadow-sm">
                <h3 className="text-style-overline uppercase text-color-foreground">
                  {t("comparison.artifactsDiff")}
                </h3>
                <div className="mt-4 grid md:grid-cols-4 gap-3 text-style-body">
                  <div className="rounded-surface border border-success-border bg-success-subtle p-3 text-color-success">
                    <strong>{comparison.artifact_diff.added.length}</strong>
                    <br />
                    {t("comparison.added")}
                  </div>
                  <div className="rounded-surface border border-danger-border bg-danger-subtle p-3 text-color-danger">
                    <strong>{comparison.artifact_diff.removed.length}</strong>
                    <br />
                    {t("comparison.removed")}
                  </div>
                  <div className="rounded-surface border border-warning-border bg-warning-subtle p-3 text-color-warning">
                    <strong>{comparison.artifact_diff.changed.length}</strong>
                    <br />
                    {t("comparison.changed")}
                  </div>
                  <div className="rounded-surface bg-muted border border-border p-3">
                    <strong>{comparison.artifact_diff.unchanged_count}</strong>
                    <br />
                    {t("comparison.unchanged")}
                  </div>
                </div>
                <div className="mt-4 max-h-64 overflow-auto rounded-surface border border-border">
                  <table className="min-w-full text-style-caption">
                    <tbody className="divide-y divide-border">
                      {comparison.artifact_diff.added.map((item) => (
                        <tr key={`added-${item.path}`}>
                          <td className="px-3 py-2 font-bold text-color-success">
                            {t("comparison.added")}
                          </td>
                          <td className="px-3 py-2 font-mono">{item.path}</td>
                          <td className="px-3 py-2">{item.kind}</td>
                        </tr>
                      ))}
                      {comparison.artifact_diff.removed.map((item) => (
                        <tr key={`removed-${item.path}`}>
                          <td className="px-3 py-2 font-bold text-color-danger">
                            {t("comparison.removed")}
                          </td>
                          <td className="px-3 py-2 font-mono">{item.path}</td>
                          <td className="px-3 py-2">{item.kind}</td>
                        </tr>
                      ))}
                      {comparison.artifact_diff.changed.map((item) => (
                        <tr key={`changed-${item.path}`}>
                          <td className="px-3 py-2 font-bold text-color-warning">
                            {t("comparison.changed")}
                          </td>
                          <td className="px-3 py-2 font-mono">{item.path}</td>
                          <td className="px-3 py-2">
                            {item.left_sha256?.slice(0, 8)} {"->"}{" "}
                            {item.right_sha256?.slice(0, 8)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>
            </div>
          ) : (
            <div className="rounded-surface border border-dashed border-border bg-surface p-10 text-center text-color-muted-foreground">
              {t("comparison.choosePrompt")}
            </div>
          )}
        </div>

        <div className="p-4 border-t border-border bg-muted flex justify-end">
          <Button variant="secondary" onClick={onClose}>
            {t("comparison.close")}
          </Button>
        </div>
      </div>
    </div>
  );
}
