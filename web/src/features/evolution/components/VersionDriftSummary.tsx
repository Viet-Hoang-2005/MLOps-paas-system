import type { DriftMonitoringJob } from "@/features/monitoring/types";
import { Badge } from "@/shared/components/Badge";
import { Button } from "@/shared/components/Button";
import { formatDateTime, formatNumber } from "@/shared/i18n/formatters";
import { getApiErrorMessage } from "@/shared/api/errors";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { versionDriftSummary } from "@/features/evolution/evolutionState";
import { buttonVariants } from "@/shared/types/buttonVariants";

export function VersionDriftSummary({
  monitors,
  projectId,
  versionId,
  loading,
  error,
  retry,
}: {
  monitors: DriftMonitoringJob[];
  projectId: string;
  versionId: string;
  loading: boolean;
  error: unknown;
  retry: () => void;
}) {
  const { t, i18n } = useTranslation("evolution");
  const owned = monitors.filter(
    (monitor) =>
      monitor.project_id === projectId && monitor.version_id === versionId,
  );
  const summary = versionDriftSummary(monitors, projectId, versionId);
  const latest = summary?.run;
  return (
    <section className="space-y-3 rounded-surface border border-border bg-muted p-4">
      <h3 className="text-style-heading">{t("workspace.drift")}</h3>
      {error ? (
        <div role="alert">
          <p>{getApiErrorMessage(error, t("workspace.driftLoadFailed"))}</p>
          <Button variant="secondary" onClick={retry}>
            {t("workspace.retry")}
          </Button>
        </div>
      ) : loading ? (
        <p role="status">{t("workspace.loading")}</p>
      ) : latest ? (
        <div className="flex flex-wrap items-center gap-3">
          <Badge
            variant={
              latest.has_drift === true
                ? "warning"
                : latest.has_drift === false
                  ? "success"
                  : "neutral"
            }
          >
            {t(
              latest.has_drift === true
                ? "workspace.driftDetected"
                : latest.has_drift === false
                  ? "workspace.noDrift"
                  : "workspace.unknown",
            )}
          </Badge>
          {latest.drift_score !== null && (
            <span>
              {t("workspace.driftScore")}:{" "}
              {formatNumber(latest.drift_score, i18n.language, {
                style: "percent",
                maximumFractionDigits: 1,
              })}
            </span>
          )}
          <time
            dateTime={latest.completed_at ?? latest.created_at}
            className="text-style-caption text-color-muted-foreground"
          >
            {formatDateTime(
              latest.completed_at ?? latest.created_at,
              i18n.language,
            )}
          </time>
        </div>
      ) : (
        <p className="text-color-muted-foreground">
          {t("workspace.noDriftRun")}
        </p>
      )}
      {owned.length > 0 && (
        <Link
          className={buttonVariants({ variant: "secondary" })}
          to={`/dashboard/projects/${projectId}/monitoring?monitorId=${summary?.monitor.id ?? owned[0].id}`}
        >
          {t("workspace.viewMonitoring")}
        </Link>
      )}
    </section>
  );
}
