import type { PreviewSingleAssetKind } from "@/features/projects/api/previewApi";
import { uploadPreviewSingleAsset } from "@/features/projects/api/previewApi";
import { getApiErrorMessage } from "@/shared/api/errors";
import { Badge } from "@/shared/components/Badge";
import { Button } from "@/shared/components/Button";
import { FileDropzone } from "@/shared/components/FileDropzone";
import { StepTitle } from "@/shared/components/StepTitle";
import { toast } from "@/shared/types/toastStore";
import { useMutation } from "@tanstack/react-query";
import { GitBranch, Lock, Upload } from "lucide-react";
import { useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

function formatBytes(bytes?: number): string {
  if (bytes === undefined || bytes === null) return "—";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

export interface AttributeDropzoneCardProps {
  title: string;
  hint: string;
  icon: ReactNode;
  kind: PreviewSingleAssetKind;
  accept: string;
  projectId: string;
  onSuccess: () => void;
  className?: string;
}

export function AttributeDropzoneCard({
  title,
  hint,
  icon,
  kind,
  accept,
  projectId,
  onSuccess,
  className = "",
}: AttributeDropzoneCardProps) {
  const { t } = useTranslation("overview");
  const [stagedFile, setStagedFile] = useState<File | null>(null);

  const handleFileChange = (file: File | null) => {
    if (!file) {
      setStagedFile(null);
      return;
    }
    if (file.size === 0) {
      toast.error(t("workflow.emptyFileError"));
      return;
    }
    const lower = file.name.toLowerCase();
    if (kind === "label_mapping") {
      if (!lower.endsWith(".json")) {
        toast.error(t("workflow.invalidLabelMappingFile"));
        return;
      }
    } else {
      if (!lower.endsWith(".json")) {
        toast.error(t("workflow.invalidJsonFile"));
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
    onSuccess: () => {
      setStagedFile(null);
      toast.success(t("workflow.attributeUploaded", { name: title }));
      onSuccess();
    },
    onError: (err) => {
      toast.error(getApiErrorMessage(err, t("workflow.uploadFailed")));
    },
  });

  return (
    <section
      className={`rounded-surface border border-border bg-surface p-6 flex flex-col justify-between ${className}`}
    >
      <div>
        <StepTitle
          icon={icon}
          title={title}
          description={hint}
          badge={
            <Badge variant="neutral">
              {t("workflow.uploadPreviewNoticeTitle")}
            </Badge>
          }
          className="mb-6"
        />

        <div className="space-y-4">
          <FileDropzone
            accept={accept}
            disabled={uploadMutation.isPending}
            title={
              stagedFile
                ? stagedFile.name
                : t("workflow.selectAttributeFile", { name: title })
            }
            subtitle={stagedFile ? formatBytes(stagedFile.size) : hint}
            hasFile={Boolean(stagedFile)}
            onRemove={() => setStagedFile(null)}
            onChange={handleFileChange}
          />

          {stagedFile && (
            <div className="flex items-center justify-between rounded-surface border border-border bg-muted p-3">
              <div className="flex items-center gap-2 truncate">
                {icon}
                <span className="truncate font-mono text-style-body-sm text-color-foreground">
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
      </div>
    </section>
  );
}

export interface AttributeMissingVersionCardProps {
  title: string;
  hint?: string;
  icon: ReactNode;
  projectId: string;
  versionId?: string;
  className?: string;
}

export function AttributeMissingVersionCard({
  title,
  hint,
  icon,
  projectId,
  versionId,
  className = "",
}: AttributeMissingVersionCardProps) {
  const { t } = useTranslation("overview");
  const navigate = useNavigate();

  return (
    <section
      className={`rounded-surface border border-border bg-surface p-6 flex flex-col justify-between ${className}`}
    >
      <div>
        <StepTitle
          icon={icon}
          title={title}
          badge={
            <Badge variant="neutral">
              <Lock className="mr-1 inline h-3 w-3" />
              {t("workflow.immutableBadge")}
            </Badge>
          }
          className="mb-6"
        />

        <div className="flex flex-col items-center justify-center rounded-surface border border-dashed border-border bg-muted/30 px-6 py-8 text-center">
          <p className="text-style-body font-medium text-color-foreground">
            {t("workflow.missingAttributeInVersion", { name: title })}
          </p>
          <p className="mt-1 max-w-md text-style-caption text-color-muted-foreground">
            {hint || t("workflow.missingAttributeInVersionHint")}
          </p>
          {versionId && (
            <Button
              className="mt-4"
              variant="secondary"
              size="sm"
              icon={<GitBranch className="h-4 w-4" />}
              onClick={() =>
                navigate(
                  `/dashboard/projects/${projectId}/evolution?versionId=${versionId}&tab=details`,
                )
              }
            >
              {t("workflow.openInEvolution")}
            </Button>
          )}
        </div>
      </div>
    </section>
  );
}

