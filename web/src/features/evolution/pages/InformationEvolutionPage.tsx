import type { Build, ModelVersion } from "@/features/projects/types";
import { Badge } from "@/shared/components/Badge";
import { CardSummary } from "@/shared/components/Card";
import { Table } from "@/shared/components/Table";
import { TextArea } from "@/shared/components/TextArea";
import { Title } from "@/shared/components/Title";
import { formatDateTime } from "@/shared/i18n/formatters";
import { buttonVariants } from "@/shared/types/buttonVariants";
import type { ColumnDef } from "@tanstack/react-table";
import {
  Activity,
  Calendar,
  Container,
  GitCommit,
  Hash,
  Layers,
  Lock,
} from "lucide-react";
import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

function formatBytes(bytes?: number): string {
  if (bytes === undefined || bytes === null) return "—";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

export interface InformationEvolutionPageProps {
  version: ModelVersion;
  build?: Build;
  runningId?: string;
}

type ArtifactItem = ModelVersion["artifacts"][number];

export function InformationEvolutionPage({
  version,
  build,
  runningId,
}: InformationEvolutionPageProps) {
  const { t, i18n } = useTranslation("evolution");

  const isRunning = version.id === runningId;

  let statusText = t("workspace.registered");
  let statusColor = "text-color-info";
  let statusTone: "default" | "success" | "warning" | "error" | "info" = "info";

  if (isRunning) {
    statusText = t("workspace.running");
    statusColor = "text-color-success";
    statusTone = "success";
  } else if (version.deployability === "invalid") {
    statusText = t("workspace.invalid");
    statusColor = "text-color-danger";
    statusTone = "error";
  } else if (version.deployability === "track_only") {
    statusText = t("workspace.track_only");
    statusColor = "text-color-warning";
    statusTone = "warning";
  }

  const imageUri =
    build?.image_uri ||
    version.artifacts.find((a) => a.kind === "model")?.name ||
    "—";

  const buildId = build?.id || "—";

  const artifactColumns = useMemo<ColumnDef<ArtifactItem>[]>(
    () => [
      {
        accessorKey: "name",
        header: t("workspace.name"),
        cell: ({ row }) => (
          <span className="font-mono font-medium text-color-foreground">
            {row.original.name}
          </span>
        ),
      },
      {
        accessorKey: "kind",
        header: t("workspace.kind"),
        cell: ({ row }) => (
          <span className="text-color-muted-foreground">
            {row.original.kind}
          </span>
        ),
      },
      {
        accessorKey: "size_bytes",
        header: t("workspace.size"),
        cell: ({ row }) => (
          <span className="text-color-muted-foreground">
            {formatBytes(row.original.size_bytes)}
          </span>
        ),
      },
      {
        accessorKey: "checksum",
        header: t("workspace.checksum"),
        cell: ({ row }) => (
          <span
            className="block truncate text-style-caption-strong text-color-muted-foreground"
            title={row.original.checksum || undefined}
          >
            {row.original.checksum || "—"}
          </span>
        ),
      },
      {
        id: "status",
        header: () => <div className="text-right">{t("workspace.status")}</div>,
        cell: () => (
          <div className="flex justify-end">
            <Badge
              variant="neutral"
              className="inline-flex items-center gap-1"
            >
              <Lock className="h-3 w-3" />
              {t("workspace.immutableBadge")}
            </Badge>
          </div>
        ),
      },
    ],
    [t],
  );

  return (
    <div className="space-y-8">
      {/* 4 CardSummary */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <CardSummary
          label={t("workspace.modelStatus")}
          value={<span className={statusColor}>{statusText}</span>}
          icon={<Activity className="h-5 w-5" />}
          tone={statusTone}
        />

        <CardSummary
          label={t("workspace.modelVersion")}
          value={`v${version.version}`}
          icon={<GitCommit className="h-5 w-5" />}
        />

        <CardSummary
          label={t("workspace.flavor")}
          value={
            <span className="font-semibold text-color-foreground">
              {version.flavor || "—"}
            </span>
          }
          icon={<Layers className="h-5 w-5" />}
        />

        <CardSummary
          label={t("workspace.registeredAt")}
          value={
            <span className="text-style-body-sm font-medium">
              {formatDateTime(version.registered_at, i18n.language)}
            </span>
          }
          icon={<Calendar className="h-5 w-5" />}
        />
      </div>

      {/* Build & Register Details */}
      <section className="space-y-4">
        <Title
          title={t("workspace.buildAndRegisterTitle")}
          action={
            version.source_job_id ? (
              <Link
                to={`/dashboard/training/jobs/${version.source_job_id}/overview`}
                className={buttonVariants({ variant: "secondary", size: "sm" })}
              >
                {t("workspace.trainingJob")}
              </Link>
            ) : null
          }
        />
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <CardSummary
            label={t("workspace.image")}
            value={
              <span
                className="block truncate font-mono text-style-code font-semibold"
                title={imageUri}
              >
                {imageUri}
              </span>
            }
            icon={<Container className="h-5 w-5" />}
          />
          <CardSummary
            label={t("workspace.buildId")}
            value={
              <span
                className="block truncate font-mono text-style-code font-semibold"
                title={buildId}
              >
                {buildId}
              </span>
            }
            icon={<Hash className="h-5 w-5" />}
          />
        </div>
      </section>

      {/* Artifacts Table */}
      <section className="space-y-4">
        <Title title={t("workspace.artifacts")} />
        <Table
          data={version.artifacts}
          columns={artifactColumns}
          getRowId={(row) => row.id || row.name}
          emptyMessage={t("workspace.noArtifacts")}
        />
      </section>

      {/* Requirements */}
      <section className="space-y-4">
        <Title title={t("workspace.requirements")} />
        <TextArea
          id="evolution-requirements"
          readOnly
          value={version.requirements_snapshot || ""}
          placeholder={t("workspace.noRequirements")}
          minHeight="min-h-48"
        />
      </section>
    </div>
  );
}

export { InformationEvolutionPage as EvolutionInformationTab };
