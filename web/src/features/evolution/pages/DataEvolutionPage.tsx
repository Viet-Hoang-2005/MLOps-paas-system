import {
  addSupplementalArtifacts,
  getVersionReferencePreview,
} from "@/features/evolution/api/evolutionApi";
import { evolutionQueryKeys } from "@/features/evolution/queryKeys";
import type { ModelVersion } from "@/features/projects/types";
import { getApiErrorMessage } from "@/shared/api/errors";
import { Badge } from "@/shared/components/Badge";
import { Button } from "@/shared/components/Button";
import { DataViewer } from "@/shared/components/DataViewer";
import { FileDropzone } from "@/shared/components/FileDropzone";
import { Loading } from "@/shared/components/Loading";
import { Placeholder } from "@/shared/components/Placeholder";
import { Title } from "@/shared/components/Title";
import { toast } from "@/shared/types/toastStore";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Download, FileSpreadsheet, Lock, Upload } from "lucide-react";
import Papa from "papaparse";
import { useState } from "react";
import { useTranslation } from "react-i18next";

const MAX_REFERENCE_DATA_BYTES = 100 * 1024 * 1024; // 100 MB

function formatBytes(bytes?: number): string {
  if (bytes === undefined || bytes === null) return "—";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

export interface DataEvolutionPageProps {
  projectId: string;
  version: ModelVersion;
}

export function DataEvolutionPage({
  projectId,
  version,
}: DataEvolutionPageProps) {
  const { t } = useTranslation("evolution");
  const queryClient = useQueryClient();

  const [stagedFile, setStagedFile] = useState<File | null>(null);

  const refArtifact = version.artifacts.find(
    (a) => a.kind === "reference_data",
  );
  const hasRefData = Boolean(refArtifact);

  const { data: refPreview, isLoading: loadingPreview } = useQuery({
    queryKey: evolutionQueryKeys.referencePreview(version.id),
    queryFn: () => getVersionReferencePreview(version.id),
    enabled: Boolean(hasRefData),
  });

  const csvContent = refPreview
    ? Papa.unparse({
        fields: refPreview.columns,
        data: refPreview.rows,
      })
    : "";
  const fileName = refArtifact?.name || "reference_data.csv";

  const handleDownload = () => {
    if (!csvContent) return;
    const blob = new Blob([csvContent], {
      type: "text/csv;charset=utf-8;",
    });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.setAttribute("download", fileName);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  };

  const handleFileChange = (file: File | null) => {
    if (!file) {
      setStagedFile(null);
      return;
    }
    if (file.size === 0) {
      toast.error(t("workspace.emptyFileError", "File is empty."));
      return;
    }
    if (file.size > MAX_REFERENCE_DATA_BYTES) {
      toast.error(t("workspace.sizeErrorRef"));
      return;
    }
    if (!file.name.toLowerCase().endsWith(".csv")) {
      toast.error(t("workspace.formatErrorRef"));
      return;
    }
    setStagedFile(file);
  };

  const uploadMutation = useMutation({
    mutationFn: async () => {
      if (!stagedFile) return;
      return await addSupplementalArtifacts(version.id, {
        reference_data_file: stagedFile,
      });
    },
    onSuccess: (updated) => {
      setStagedFile(null);
      toast.success(t("workspace.supplementalSuccess"));
      queryClient.setQueryData(
        evolutionQueryKeys.snapshot(version.id),
        updated,
      );
      void queryClient.invalidateQueries({
        queryKey: evolutionQueryKeys.versions(projectId),
      });
      void queryClient.invalidateQueries({
        queryKey: evolutionQueryKeys.snapshot(version.id),
      });
      void queryClient.invalidateQueries({
        queryKey: evolutionQueryKeys.referencePreview(version.id),
      });
      void queryClient.invalidateQueries({
        queryKey: ["overview"],
      });
      void queryClient.invalidateQueries({
        queryKey: ["catalog", "projects"],
      });
    },
    onError: (err) => {
      toast.error(
        getApiErrorMessage(err, t("workspace.supplementalFailed")),
      );
    },
  });

  if (hasRefData) {
    if (loadingPreview) {
      return (
        <Placeholder role="tabpanel" className="flex-1 min-h-105">
          <Loading
            size="lg"
            text={t("workspace.loadingData", "Loading reference data…")}
          />
        </Placeholder>
      );
    }

    return (
      <div className="space-y-4">
        <div className="overflow-hidden rounded-surface border border-border bg-surface">
          <DataViewer
            initialCsvText={csvContent}
            readOnly={true}
            title={fileName}
            icon={<FileSpreadsheet className="h-5 w-5 text-color-primary" />}
            badge={
              <Badge variant="neutral">
                <Lock className="mr-1 inline h-3 w-3" />
                {t("workspace.immutableBadge")}
              </Badge>
            }
            actionButtons={[
              {
                label: t("workspace.download", "Download"),
                icon: <Download className="h-4 w-4" />,
                variant: "secondary",
                onClick: handleDownload,
              },
            ]}
          />
        </div>
      </div>
    );
  }

  return (
    <section className="rounded-surface border border-border bg-surface p-6 space-y-6">
      <Title
        icon={<FileSpreadsheet className="h-5 w-5 text-color-primary" />}
        title={t("workspace.addReferenceData")}
        description={t("workspace.uploadRefHint")}
        badge={
          <Badge variant="neutral">
            {t("workspace.supplementalNotice", "One-time upload")}
          </Badge>
        }
      />

      <div className="space-y-4 max-w-2xl">
        <FileDropzone
          accept=".csv"
          title={t(
            "workspace.dragRefData",
            "Drag & drop CSV file (.csv) or browse",
          )}
          subtitle={t(
            "workspace.maxRefSize",
            "Supported: .csv, max 100MB",
          )}
          hint={t(
            "workspace.supplementalHint",
            "File will become immutable once registered.",
          )}
          onChange={handleFileChange}
          hasFile={Boolean(stagedFile)}
        />

        {stagedFile && (
          <div className="flex items-center justify-between rounded-surface border border-border bg-muted/30 p-4">
            <div className="min-w-0 pr-4">
              <p className="truncate font-mono text-style-body-sm font-semibold text-color-foreground">
                {stagedFile.name}
              </p>
              <p className="text-style-caption text-color-muted-foreground">
                {formatBytes(stagedFile.size)}
              </p>
            </div>
            <div className="flex items-center gap-2">
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setStagedFile(null)}
              >
                {t("workspace.clear")}
              </Button>
              <Button
                variant="primary"
                size="sm"
                icon={<Upload className="h-4 w-4" />}
                loading={uploadMutation.isPending}
                onClick={() => uploadMutation.mutate()}
              >
                {t("workspace.upload")}
              </Button>
            </div>
          </div>
        )}
      </div>
    </section>
  );
}

export { DataEvolutionPage as EvolutionDataTab };

