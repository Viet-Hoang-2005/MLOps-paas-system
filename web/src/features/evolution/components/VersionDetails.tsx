import type { Build, ModelVersion } from "@/features/projects/types";
import { Badge } from "@/shared/components/Badge";
import { buttonVariants } from "@/shared/types/buttonVariants";
import { VersionRecords } from "./VersionRecords";
import { formatDateTime, formatNumber } from "@/shared/i18n/formatters";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { Package, FileCode2 } from "lucide-react";

export function VersionDetails({
  version,
  build,
}: {
  version: ModelVersion;
  build?: Build;
}) {
  const { t, i18n } = useTranslation("evolution");
  const properties = [
    [t("workspace.flavor"), version.flavor],
    [
      t("workspace.source"),
      t(version.source_job_id ? "workspace.trained" : "workspace.preview"),
    ],
    [
      t("workspace.registeredAt"),
      formatDateTime(version.registered_at, i18n.language),
    ],
    [t("workspace.buildId"), build?.id],
    [t("workspace.image"), build?.image_uri],
  ];
  const status = version.deployability;
  return (
    <div className="space-y-6">
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <div className="rounded-surface border border-border bg-muted p-4">
          <p className="mb-2 text-style-caption text-color-muted-foreground">
            {t("workspace.deployability")}
          </p>
          <Badge
            variant={
              status === "deployable"
                ? "success"
                : status === "invalid"
                  ? "danger"
                  : "neutral"
            }
          >
            {t(
              status === "deployable"
                ? "workspace.deployable"
                : status === "track_only"
                  ? "workspace.track_only"
                  : status === "invalid"
                    ? "workspace.invalid"
                    : "workspace.unknown",
            )}
          </Badge>
          {version.deployability_reason && (
            <p className="mt-2 text-style-caption">
              {version.deployability_reason}
            </p>
          )}
        </div>
        <div className="rounded-surface border border-border bg-muted p-4">
          <Package className="mb-2 h-5 w-5 text-color-primary" />
          <p className="text-style-caption text-color-muted-foreground">
            {t("workspace.artifactCount")}
          </p>
          <p className="text-style-metric">
            {formatNumber(version.artifacts.length, i18n.language)}
          </p>
        </div>
        {version.source_job_id && (
          <div className="rounded-surface border border-border bg-muted p-4">
            <FileCode2 className="mb-2 h-5 w-5 text-color-primary" />
            <Link
              className={buttonVariants({ variant: "secondary" })}
              to={`/dashboard/training/jobs/${version.source_job_id}/overview`}
            >
              {t("workspace.trainingJob")}
            </Link>
            <p className="mt-2 break-all text-style-code-sm">
              {version.source_job_id}
            </p>
          </div>
        )}
      </div>
      <dl className="grid gap-4 rounded-surface border border-border p-4 sm:grid-cols-2">
        {properties.map(([label, value]) => (
          <div key={label}>
            <dt className="text-style-caption text-color-muted-foreground">
              {label}
            </dt>
            <dd className="mt-1 break-all text-style-body-strong">
              {value || t("workspace.missing")}
            </dd>
          </div>
        ))}
      </dl>
      <section className="space-y-3">
        <h3 className="text-style-heading">{t("workspace.artifacts")}</h3>
        <VersionRecords
          rows={version.artifacts.map((artifact) => ({
            name: artifact.name,
            kind: artifact.kind,
            checksum: artifact.checksum,
            size: formatNumber(artifact.size_bytes, i18n.language, {
              style: "unit",
              unit: "byte",
              unitDisplay: "short",
            }),
          }))}
          columns={[
            { key: "name", title: t("workspace.name") },
            { key: "kind", title: t("workspace.kind") },
            { key: "size", title: t("workspace.size") },
            { key: "checksum", title: t("workspace.checksum") },
          ]}
          empty={t("workspace.noArtifacts")}
        />
      </section>
      <section className="space-y-3">
        <h3 className="text-style-heading">{t("workspace.parameters")}</h3>
        <VersionRecords
          rows={Object.entries(version.params_summary).map(([name, value]) => ({
            name,
            value,
          }))}
          columns={[
            { key: "name", title: t("workspace.name") },
            { key: "value", title: t("workspace.value") },
          ]}
          empty={t("workspace.noParameters")}
        />
      </section>
      <section className="space-y-3">
        <h3 className="text-style-heading">{t("workspace.requirements")}</h3>
        <pre className="max-h-80 overflow-auto rounded-surface border border-border bg-muted p-4 text-style-code-sm">
          {version.requirements_snapshot || t("workspace.noRequirements")}
        </pre>
      </section>
    </div>
  );
}
