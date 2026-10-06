import {
  addSupplementalArtifacts,
  getVersionReferencePreview,
} from "@/features/evolution/api/evolutionApi";
import { evolutionQueryKeys } from "@/features/evolution/queryKeys";
import type { Build, ModelVersion } from "@/features/projects/types";
import { getApiErrorMessage } from "@/shared/api/errors";
import { Badge } from "@/shared/components/Badge";
import BaseDialog from "@/shared/components/BaseDialog";
import { Button } from "@/shared/components/Button";
import { formatDateTime, formatNumber } from "@/shared/i18n/formatters";
import { buttonVariants } from "@/shared/types/buttonVariants";
import { toast } from "@/shared/types/toastStore";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Code2,
  Eye,
  FileCode2,
  FileSpreadsheet,
  Lock,
  Package,
  RefreshCw,
  Upload,
} from "lucide-react";
import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { VersionRecords } from "./VersionRecords";

const MAX_SOURCE_CODE_BYTES = 5 * 1024 * 1024; // < 5 MB
const MAX_REFERENCE_DATA_BYTES = 100 * 1024 * 1024; // < 100 MB

function formatBytes(bytes?: number): string {
  if (bytes === undefined || bytes === null) return "—";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

export function VersionDetails({
  version,
  build,
}: {
  version: ModelVersion;
  build?: Build;
}) {
  const { t, i18n } = useTranslation("evolution");
  const queryClient = useQueryClient();

  const sourceFileInputRef = useRef<HTMLInputElement>(null);
  const refFileInputRef = useRef<HTMLInputElement>(null);

  const [stagedSourceFile, setStagedSourceFile] = useState<File | null>(null);
  const [stagedRefFile, setStagedRefFile] = useState<File | null>(null);
  const [previewOpen, setPreviewOpen] = useState(false);

  const hasSourceCode = version.artifacts.some(
    (a) => a.kind === "source_code",
  );
  const hasRefData = version.artifacts.some((a) => a.kind === "reference_data");
  const refArtifact = version.artifacts.find(
    (a) => a.kind === "reference_data",
  );

  // Reference preview query
  const {
    data: refPreview,
    isLoading: loadingPreview,
    error: previewError,
  } = useQuery({
    queryKey: evolutionQueryKeys.referencePreview(version.id),
    queryFn: () => getVersionReferencePreview(version.id),
    enabled: Boolean(previewOpen && hasRefData),
  });

  // Supplemental artifact mutation
  const uploadMutation = useMutation({
    mutationFn: async () => {
      return await addSupplementalArtifacts(version.id, {
        source_code_file: stagedSourceFile || undefined,
        reference_data_file: stagedRefFile || undefined,
      });
    },
    onSuccess: (updated) => {
      setStagedSourceFile(null);
      setStagedRefFile(null);
      queryClient.setQueryData(
        evolutionQueryKeys.snapshot(version.id),
        updated,
      );
      void queryClient.invalidateQueries({
        queryKey: evolutionQueryKeys.versions(version.project_id),
      });
      void queryClient.invalidateQueries({
        queryKey: evolutionQueryKeys.snapshot(version.id),
      });
      toast.success(t("workspace.supplementalSuccess"));
    },
    onError: (err) => {
      toast.error(
        getApiErrorMessage(err, t("workspace.supplementalFailed")),
      );
    },
  });

  const handleSourceFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    if (!file.name.toLowerCase().endsWith(".py")) {
      toast.error(t("workspace.formatErrorSource"));
      e.target.value = "";
      return;
    }
    if (file.size > MAX_SOURCE_CODE_BYTES) {
      toast.error(t("workspace.sizeErrorSource"));
      e.target.value = "";
      return;
    }

    setStagedSourceFile(file);
    e.target.value = "";
  };

  const handleRefFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    const lower = file.name.toLowerCase();
    if (!lower.endsWith(".csv") && !lower.endsWith(".parquet")) {
      toast.error(t("workspace.formatErrorRef"));
      e.target.value = "";
      return;
    }
    if (file.size > MAX_REFERENCE_DATA_BYTES) {
      toast.error(t("workspace.sizeErrorRef"));
      e.target.value = "";
      return;
    }

    setStagedRefFile(file);
    e.target.value = "";
  };

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

      {/* Supplemental Artifacts Card (only if missing source_code or reference_data) */}
      {(!hasSourceCode || !hasRefData) && (
        <section className="rounded-surface border border-primary/20 bg-primary-subtle/10 p-5 space-y-4">
          <div>
            <div className="flex items-center gap-2">
              <Upload className="h-5 w-5 text-color-primary" />
              <h3 className="text-style-body-strong font-semibold text-color-foreground">
                {t("workspace.supplementalArtifacts")}
              </h3>
            </div>
            <p className="mt-1 text-style-caption text-color-muted-foreground">
              {t("workspace.supplementalDesc")}
            </p>
          </div>

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            {/* Source code upload slot */}
            {!hasSourceCode && (
              <div className="rounded-surface border border-border bg-surface p-4 space-y-3">
                <div className="flex items-center gap-2">
                  <Code2 className="h-4 w-4 text-color-primary" />
                  <span className="text-style-body-sm font-semibold text-color-foreground">
                    {t("workspace.addSourceCode")}
                  </span>
                </div>
                <p className="text-style-caption text-color-muted-foreground">
                  {t("workspace.uploadSourceHint")}
                </p>
                <input
                  type="file"
                  ref={sourceFileInputRef}
                  accept=".py"
                  className="hidden"
                  onChange={handleSourceFileSelect}
                />
                {stagedSourceFile ? (
                  <div className="flex items-center justify-between rounded-surface bg-muted p-2 text-style-caption">
                    <span className="truncate font-mono">
                      {stagedSourceFile.name} ({formatBytes(stagedSourceFile.size)})
                    </span>
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => setStagedSourceFile(null)}
                    >
                      {t("workspace.clear")}
                    </Button>
                  </div>
                ) : (
                  <Button
                    size="sm"
                    variant="secondary"
                    icon={<Upload className="h-4 w-4" />}
                    onClick={() => sourceFileInputRef.current?.click()}
                  >
                    {t("workspace.selectSourceFile")}
                  </Button>
                )}
              </div>
            )}

            {/* Reference data upload slot */}
            {!hasRefData && (
              <div className="rounded-surface border border-border bg-surface p-4 space-y-3">
                <div className="flex items-center gap-2">
                  <FileSpreadsheet className="h-4 w-4 text-color-primary" />
                  <span className="text-style-body-sm font-semibold text-color-foreground">
                    {t("workspace.addReferenceData")}
                  </span>
                </div>
                <p className="text-style-caption text-color-muted-foreground">
                  {t("workspace.uploadRefHint")}
                </p>
                <input
                  type="file"
                  ref={refFileInputRef}
                  accept=".csv,.parquet"
                  className="hidden"
                  onChange={handleRefFileSelect}
                />
                {stagedRefFile ? (
                  <div className="flex items-center justify-between rounded-surface bg-muted p-2 text-style-caption">
                    <span className="truncate font-mono">
                      {stagedRefFile.name} ({formatBytes(stagedRefFile.size)})
                    </span>
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => setStagedRefFile(null)}
                    >
                      {t("workspace.clear")}
                    </Button>
                  </div>
                ) : (
                  <Button
                    size="sm"
                    variant="secondary"
                    icon={<Upload className="h-4 w-4" />}
                    onClick={() => refFileInputRef.current?.click()}
                  >
                    {t("workspace.selectRefFile")}
                  </Button>
                )}
              </div>
            )}
          </div>

          {(stagedSourceFile || stagedRefFile) && (
            <div className="flex justify-end pt-2">
              <Button
                variant="primary"
                icon={<Upload className="h-4 w-4" />}
                loading={uploadMutation.isPending}
                onClick={() => uploadMutation.mutate()}
              >
                {t("workspace.upload")}
              </Button>
            </div>
          )}
        </section>
      )}

      {/* Registered Artifacts List */}
      <section className="space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="text-style-heading">{t("workspace.artifacts")}</h3>
          {hasRefData && (
            <Button
              size="sm"
              variant="secondary"
              icon={<Eye className="h-4 w-4" />}
              onClick={() => setPreviewOpen(true)}
            >
              {t("workspace.previewDataset")}
            </Button>
          )}
        </div>

        <div className="overflow-hidden rounded-surface border border-border">
          <table className="min-w-full divide-y divide-border border-collapse text-left text-style-body-sm">
            <thead className="bg-muted">
              <tr>
                <th className="px-4 py-3 font-semibold text-color-foreground">
                  {t("workspace.name")}
                </th>
                <th className="px-4 py-3 font-semibold text-color-foreground">
                  {t("workspace.kind")}
                </th>
                <th className="px-4 py-3 font-semibold text-color-foreground">
                  {t("workspace.size")}
                </th>
                <th className="px-4 py-3 font-semibold text-color-foreground">
                  {t("workspace.checksum")}
                </th>
                <th className="px-4 py-3 font-semibold text-color-foreground text-right">
                  {t("workspace.status")}
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border bg-surface">
              {version.artifacts.length === 0 ? (
                <tr>
                  <td
                    colSpan={5}
                    className="px-4 py-8 text-center text-color-muted-foreground"
                  >
                    {t("workspace.noArtifacts")}
                  </td>
                </tr>
              ) : (
                version.artifacts.map((artifact) => (
                  <tr key={artifact.id || artifact.name} className="hover:bg-muted/40">
                    <td className="px-4 py-3 font-mono text-color-foreground font-medium">
                      {artifact.name}
                    </td>
                    <td className="px-4 py-3 text-color-muted-foreground">
                      {artifact.kind}
                    </td>
                    <td className="px-4 py-3 text-color-muted-foreground">
                      {formatBytes(artifact.size_bytes)}
                    </td>
                    <td className="px-4 py-3 font-mono text-style-caption text-color-muted-foreground max-w-45 truncate">
                      {artifact.checksum || "—"}
                    </td>
                    <td className="px-4 py-3 text-right">
                      <Badge variant="neutral" className="inline-flex items-center gap-1">
                        <Lock className="h-3 w-3" />
                        {t("workspace.immutableBadge")}
                      </Badge>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </section>

      <section className="space-y-3">
        <h3 className="text-style-heading">{t("workspace.parameters")}</h3>
        <VersionRecords
          rows={Object.entries(version.params_summary).map(
            ([name, value]) => ({
              name,
              value,
            }),
          )}
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

      {/* Dataset Preview Modal */}
      {previewOpen && (
        <BaseDialog
          title={t("workspace.previewDatasetTitle", {
            name: refArtifact?.name || "Reference Dataset",
          })}
          className="w-[min(94vw,56rem)]"
          onClose={() => setPreviewOpen(false)}
        >
          <div className="space-y-4">
            {loadingPreview ? (
              <div className="flex h-48 items-center justify-center">
                <RefreshCw className="h-6 w-6 animate-spin text-color-primary" />
              </div>
            ) : previewError || !refPreview ? (
              <div className="rounded-surface border border-border p-6 text-center text-style-body text-color-muted-foreground">
                {getApiErrorMessage(
                  previewError,
                  t("workspace.previewEmpty"),
                )}
              </div>
            ) : (
              <div className="space-y-2">
                <div className="flex justify-between text-style-caption text-color-muted-foreground">
                  <span className="font-mono">
                    {t("workspace.formatLabel")} {refPreview.format.toUpperCase()}
                  </span>
                  <span>
                    {t("workspace.previewRows", {
                      count: refPreview.rows.length,
                      total: refPreview.total_rows,
                    })}
                  </span>
                </div>
                <div className="max-h-96 overflow-auto rounded-surface border border-border">
                  <table className="min-w-full divide-y divide-border border-collapse text-left text-style-caption">
                    <thead className="sticky top-0 bg-muted/90 backdrop-blur z-10">
                      <tr>
                        <th className="px-3 py-2 font-semibold text-color-muted-foreground w-12 border-r border-border">
                          #
                        </th>
                        {refPreview.columns.map((col, idx) => (
                          <th
                            key={idx}
                            className="px-3 py-2 font-semibold text-color-foreground border-r border-border whitespace-nowrap"
                          >
                            {col}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-border bg-surface">
                      {refPreview.rows.map((row, rIdx) => (
                        <tr key={rIdx} className="hover:bg-muted/30">
                          <td className="px-3 py-1.5 text-color-muted-foreground border-r border-border font-mono">
                            {rIdx + 1}
                          </td>
                          {row.map((cell, cIdx) => (
                            <td
                              key={cIdx}
                              className="px-3 py-1.5 text-color-foreground border-r border-border whitespace-nowrap font-mono"
                            >
                              {cell === null ? (
                                <span className="text-color-muted-foreground italic">
                                  {t("workspace.nullValue")}
                                </span>
                              ) : (
                                String(cell)
                              )}
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
            <div className="flex justify-end pt-2">
              <Button variant="secondary" onClick={() => setPreviewOpen(false)}>
                {t("workspace.close")}
              </Button>
            </div>
          </div>
        </BaseDialog>
      )}
    </div>
  );
}

