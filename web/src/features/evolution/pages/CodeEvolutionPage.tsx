import { useTheme } from "@/app/theme/useTheme";
import { addSupplementalArtifacts } from "@/features/evolution/api/evolutionApi";
import { evolutionQueryKeys } from "@/features/evolution/queryKeys";
import {
  useRunningSource,
  overviewQueryKeys,
} from "@/features/overview/hooks/useProjectOverview";
import type { ModelVersion } from "@/features/projects/types";
import { getApiErrorMessage } from "@/shared/api/errors";
import { Badge } from "@/shared/components/Badge";
import { Button } from "@/shared/components/Button";
import { CodeViewer } from "@/shared/components/CodeViewer";
import { FileDropzone } from "@/shared/components/FileDropzone";
import { Loading } from "@/shared/components/Loading";
import { Placeholder } from "@/shared/components/Placeholder";
import { Title } from "@/shared/components/Title";
import { toast } from "@/shared/types/toastStore";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Code, Download, Lock, Upload } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";

const MAX_SOURCE_CODE_BYTES = 5 * 1024 * 1024; // 5 MB

function formatBytes(bytes?: number): string {
  if (bytes === undefined || bytes === null) return "—";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

export interface CodeEvolutionPageProps {
  projectId: string;
  version: ModelVersion;
}

export function CodeEvolutionPage({
  projectId,
  version,
}: CodeEvolutionPageProps) {
  const { t } = useTranslation("evolution");
  const { resolvedTheme } = useTheme();
  const queryClient = useQueryClient();

  const [stagedFile, setStagedFile] = useState<File | null>(null);
  const sourceArtifact = version.artifacts.find(
    (a) => a.kind === "source_code",
  );
  const hasSourceCode = Boolean(sourceArtifact);

  const sourceQuery = useRunningSource(
    hasSourceCode ? projectId : undefined,
    hasSourceCode ? version.id : undefined,
  );

  const codeContent = sourceQuery.data || "";
  const fileName = sourceArtifact?.name || "train.py";

  const handleDownload = () => {
    if (!codeContent) return;
    const blob = new Blob([codeContent], {
      type: "text/x-python;charset=utf-8;",
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
    if (file.size > MAX_SOURCE_CODE_BYTES) {
      toast.error(t("workspace.sizeErrorSource"));
      return;
    }
    if (!file.name.toLowerCase().endsWith(".py")) {
      toast.error(t("workspace.formatErrorSource"));
      return;
    }
    setStagedFile(file);
  };

  const uploadMutation = useMutation({
    mutationFn: async () => {
      if (!stagedFile) return;
      return await addSupplementalArtifacts(version.id, {
        source_code_file: stagedFile,
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
        queryKey: overviewQueryKeys.source(projectId, version.id),
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

  if (hasSourceCode) {
    if (sourceQuery.isLoading) {
      return (
        <Placeholder role="tabpanel" className="flex-1 min-h-105">
          <Loading
            size="lg"
            text={t("workspace.loadingCode", "Loading source code…")}
          />
        </Placeholder>
      );
    }

    return (
      <div className="flex-1 min-h-0 h-full flex flex-col">
        <CodeViewer
          value={codeContent}
          language="python"
          theme={resolvedTheme === "dark" ? "vs-dark" : "light"}
          title={fileName}
          icon={<Code className="h-5 w-5 text-color-primary" />}
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
          options={{
            readOnly: true,
            minimap: { enabled: false },
            scrollBeyondLastLine: false,
            automaticLayout: true,
          }}
        />
      </div>
    );
  }

  return (
    <section className="rounded-surface border border-border bg-surface p-6 space-y-6">
      <Title
        icon={<Code className="h-5 w-5 text-color-primary" />}
        title={t("workspace.addSourceCode")}
        description={t("workspace.uploadSourceHint")}
        badge={
          <Badge variant="neutral">
            {t("workspace.supplementalNotice", "One-time upload")}
          </Badge>
        }
      />

      <div className="space-y-4 max-w-2xl">
        <FileDropzone
          accept=".py"
          title={t(
            "workspace.dragSourceCode",
            "Drag & drop Python file (.py) or browse",
          )}
          subtitle={t(
            "workspace.maxSourceSize",
            "Supported: .py, max 5MB",
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

export { CodeEvolutionPage as EvolutionCodeTab };

