import {
  addSupplementalArtifacts,
  type SupplementalArtifactsPayload,
} from "@/features/evolution/api/evolutionApi";
import { evolutionQueryKeys } from "@/features/evolution/queryKeys";
import { overviewQueryKeys } from "@/features/overview/queryKeys";
import { getApiErrorMessage } from "@/shared/api/errors";
import { Badge } from "@/shared/components/Badge";
import { Button } from "@/shared/components/Button";
import { FileDropzone } from "@/shared/components/FileDropzone";
import { Title } from "@/shared/components/Title";
import { toast } from "@/shared/types/toastStore";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Upload } from "lucide-react";
import { useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";

function formatBytes(bytes?: number): string {
  if (bytes === undefined || bytes === null) return "—";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

export type SupplementalAttributeKind =
  | "label_mapping"
  | "input_schema"
  | "metrics"
  | "params"
  | "model_insights"
  | "feature_importance";

export interface AttributeDropzoneProps {
  title: string;
  hint: string;
  icon: ReactNode;
  kind: SupplementalAttributeKind;
  versionId: string;
  projectId: string;
  onSuccess?: () => void;
  className?: string;
}

export function AttributeDropzoneCard({
  title,
  hint,
  icon,
  kind,
  versionId,
  projectId,
  onSuccess,
  className = "",
}: AttributeDropzoneProps) {
  const { t } = useTranslation("evolution");
  const queryClient = useQueryClient();
  const [stagedFile, setStagedFile] = useState<File | null>(null);

  const handleFileChange = (file: File | null) => {
    if (!file) {
      setStagedFile(null);
      return;
    }
    if (file.size === 0) {
      toast.error(t("workspace.emptyFileError", "File is empty."));
      return;
    }
    if (file.size > 4 * 1024 * 1024) {
      toast.error(t("workspace.invalidSupplementalJson"));
      return;
    }
    if (!file.name.toLowerCase().endsWith(".json")) {
      toast.error(t("workspace.invalidSupplementalJson"));
      return;
    }
    setStagedFile(file);
  };

  const uploadMutation = useMutation({
    mutationFn: async () => {
      if (!stagedFile) return;
      const payload: SupplementalArtifactsPayload = {
        [`${kind}_file`]: stagedFile,
      };
      return await addSupplementalArtifacts(versionId, payload);
    },
    onSuccess: (updated) => {
      setStagedFile(null);
      toast.success(t("workspace.supplementalSuccess"));
      queryClient.setQueryData(
        evolutionQueryKeys.snapshot(versionId),
        updated,
      );
      void queryClient.invalidateQueries({
        queryKey: evolutionQueryKeys.versions(projectId),
      });
      void queryClient.invalidateQueries({
        queryKey: evolutionQueryKeys.snapshot(versionId),
      });
      void queryClient.invalidateQueries({
        queryKey: overviewQueryKeys.attributes(projectId, versionId),
      });
      void queryClient.invalidateQueries({
        queryKey: ["catalog", "projects"],
      });
      onSuccess?.();
    },
    onError: (err) => {
      toast.error(
        getApiErrorMessage(err, t("workspace.supplementalFailed")),
      );
    },
  });

  return (
    <section
      className={`rounded-surface border border-border bg-surface p-6 flex flex-col justify-between ${className}`}
    >
      <div>
        <Title
          icon={icon}
          title={title}
          description={hint}
          badge={
            <Badge variant="neutral">
              {t("workspace.supplementalNotice", "One-time upload")}
            </Badge>
          }
          className="mb-6"
        />

        <div className="space-y-4">
          <FileDropzone
            accept=".json"
            title={t(
              "workspace.dragSupplementalJson",
              "Drag & drop JSON file or browse",
            )}
            subtitle={t(
              "workspace.maxJsonSize",
              "Supported: .json, max 4MB",
            )}
            hint={t(
              "workspace.supplementalHint",
              "File will become immutable once registered.",
            )}
            onChange={handleFileChange}
            hasFile={Boolean(stagedFile)}
          />

          {stagedFile && (
            <div className="flex items-center justify-between rounded-surface border border-border bg-muted/30 p-3">
              <div className="min-w-0 pr-3">
                <p className="truncate font-mono text-style-caption font-medium text-color-foreground">
                  {stagedFile.name}
                </p>
                <p className="text-style-caption text-color-muted-foreground">
                  {formatBytes(stagedFile.size)}
                </p>
              </div>
              <div className="flex items-center gap-2">
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => setStagedFile(null)}
                >
                  {t("workspace.clear")}
                </Button>
                <Button
                  size="sm"
                  variant="primary"
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
      </div>
    </section>
  );
}

