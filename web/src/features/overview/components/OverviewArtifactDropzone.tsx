import { overviewQueryKeys } from "@/features/overview/queryKeys";
import { uploadPreviewSingleAsset } from "@/features/projects/api/previewApi";
import { previewKeys } from "@/features/projects/hooks/usePreview";
import { getApiErrorMessage } from "@/shared/api/errors";
import { Badge } from "@/shared/components/Badge";
import { Button } from "@/shared/components/Button";
import { Callout } from "@/shared/components/Callout";
import { FileDropzone } from "@/shared/components/FileDropzone";
import { cn } from "@/shared/lib/cn";
import { toast } from "@/shared/types/toastStore";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Code2, FileSpreadsheet, Upload } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";

const MAX_SOURCE_CODE_BYTES = 5 * 1024 * 1024; // 5 MB
const MAX_REFERENCE_DATA_BYTES = 100 * 1024 * 1024; // 100 MB

function formatBytes(bytes?: number): string {
  if (bytes === undefined || bytes === null) return "—";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

interface OverviewArtifactDropzoneProps {
  projectId: string;
  kind: "source_code" | "reference_data";
  className?: string;
  onUploadSuccess?: () => void | Promise<void>;
}

export function OverviewArtifactDropzone({
  projectId,
  kind,
  className,
  onUploadSuccess,
}: OverviewArtifactDropzoneProps) {
  const { t } = useTranslation("overview");
  const client = useQueryClient();
  const [stagedFile, setStagedFile] = useState<File | null>(null);

  const isSource = kind === "source_code";

  const handleFileChange = (file: File | null) => {
    if (!file) {
      setStagedFile(null);
      return;
    }

    if (file.size === 0) {
      toast.error(t("workflow.emptyFileError"));
      return;
    }

    if (isSource) {
      if (!file.name.toLowerCase().endsWith(".py")) {
        toast.error(t("workflow.formatErrorSource"));
        return;
      }
      if (file.size > MAX_SOURCE_CODE_BYTES) {
        toast.error(t("workflow.sizeErrorSource"));
        return;
      }
    } else {
      if (!file.name.toLowerCase().endsWith(".csv")) {
        toast.error(t("workflow.formatErrorRef"));
        return;
      }
      if (file.size > MAX_REFERENCE_DATA_BYTES) {
        toast.error(t("workflow.sizeErrorRef"));
        return;
      }
    }

    setStagedFile(file);
  };

  const uploadMutation = useMutation({
    mutationFn: async () => {
      if (!stagedFile) return;
      return await uploadPreviewSingleAsset(projectId, kind, stagedFile);
    },
    onSuccess: async () => {
      setStagedFile(null);
      toast.success(t("workflow.uploadSuccess"));
      await Promise.all([
        client.invalidateQueries({
          queryKey: previewKeys.detail(projectId),
        }),
        client.invalidateQueries({
          queryKey: overviewQueryKeys.detail(projectId),
        }),
      ]);
      if (onUploadSuccess) {
        await onUploadSuccess();
      }
    },
    onError: (err) => {
      toast.error(getApiErrorMessage(err, t("workflow.uploadFailed")));
    },
  });

  return (
    <div className={cn("flex flex-1 flex-col space-y-4", className)}>
      <Callout
        variant="info"
        icon={
          isSource ? (
            <Code2 className="h-5 w-5" />
          ) : (
            <FileSpreadsheet className="h-5 w-5" />
          )
        }
        title={
          <div className="flex items-center gap-2">
            <span>
              {isSource
                ? t("workflow.uploadSourceTitle")
                : t("workflow.uploadRefTitle")}
            </span>
            <Badge variant="neutral">
              {t("workflow.uploadPreviewNoticeTitle")}
            </Badge>
          </div>
        }
        description={t("workflow.uploadPreviewNotice")}
      />

      <FileDropzone
        className="flex-1"
        accept={isSource ? ".py" : ".csv"}
        disabled={uploadMutation.isPending}
        title={
          stagedFile
            ? stagedFile.name
            : isSource
              ? t("workflow.selectSourceFile")
              : t("workflow.selectRefFile")
        }
        subtitle={
          stagedFile
            ? formatBytes(stagedFile.size)
            : isSource
              ? t("workflow.uploadSourceSubtitle")
              : t("workflow.uploadRefSubtitle")
        }
        hint={t("workflow.uploadPreviewHint")}
        hasFile={Boolean(stagedFile)}
        onRemove={() => setStagedFile(null)}
        onChange={handleFileChange}
      />

      {stagedFile && (
        <div className="flex items-center justify-between rounded-surface border border-border bg-muted p-3">
          <div className="flex items-center gap-2 truncate">
            {isSource ? (
              <Code2 className="h-4 w-4 text-color-primary shrink-0" />
            ) : (
              <FileSpreadsheet className="h-4 w-4 text-color-primary shrink-0" />
            )}
            <span className="truncate text-style-body-sm font-mono text-color-foreground">
              {stagedFile.name}
            </span>
            <span className="text-style-caption text-color-muted-foreground">
              ({formatBytes(stagedFile.size)})
            </span>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <Button
              size="sm"
              variant="ghost"
              disabled={uploadMutation.isPending}
              onClick={() => setStagedFile(null)}
            >
              {t("workflow.clear")}
            </Button>
            <Button
              size="sm"
              variant="primary"
              icon={<Upload className="h-4 w-4" />}
              loading={uploadMutation.isPending}
              onClick={() => uploadMutation.mutate()}
            >
              {t("workflow.upload")}
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
