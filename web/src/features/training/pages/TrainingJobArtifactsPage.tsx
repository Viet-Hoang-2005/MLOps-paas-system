import { useTheme } from "@/app/theme/useTheme";
import { buildDeploymentPath } from "@/features/deployments/navigation";
import {
  getJobReferencePreview,
  getModelOutputSummary,
  patchModelOutput,
} from "@/features/training/api/trainingApi";
import { trainingQueryKeys } from "@/features/training/queryKeys";
import { useTrainingJobDetailContext } from "@/features/training/trainingJobDetailContext";
import { getApiErrorMessage } from "@/shared/api/errors";
import { Badge } from "@/shared/components/Badge";
import { Button } from "@/shared/components/Button";
import { Callout } from "@/shared/components/Callout";
import { ConfirmDialog } from "@/shared/components/ConfirmDialog";
import { CodeViewer } from "@/shared/components/CodeViewer";
import { toast } from "@/shared/types/toastStore";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertCircle,
  BarChart2,
  CheckCircle2,
  Code2,
  Database,
  Download,
  FileCode,
  FileSpreadsheet,
  Lock,
  RefreshCw,
  Rocket,
  Save,
  Trash2,
  Upload,
} from "lucide-react";
import { useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

const MAX_SOURCE_CODE_BYTES = 5 * 1024 * 1024; // < 5 MB
const MAX_REFERENCE_DATA_BYTES = 100 * 1024 * 1024; // < 100 MB

function formatBytes(bytes?: number): string {
  if (bytes === undefined || bytes === null) return "—";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

export default function TrainingJobArtifactsPage() {
  const { t } = useTranslation("training");
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { resolvedTheme } = useTheme();
  const { job, downloadingOutput, downloadOutput, requestDeleteOutputs } =
    useTrainingJobDetailContext();

  const sourceFileInputRef = useRef<HTMLInputElement>(null);
  const refFileInputRef = useRef<HTMLInputElement>(null);

  // Output summary query
  const {
    data: summary,
    isLoading: loadingSummary,
    error: summaryError,
    refetch: refetchSummary,
  } = useQuery({
    queryKey: trainingQueryKeys.modelOutput(job.id),
    queryFn: () => getModelOutputSummary(job.id),
    enabled: Boolean(job.id),
  });

  // Reference preview query
  const {
    data: refPreview,
    isLoading: loadingPreview,
    error: previewError,
    refetch: refetchPreview,
  } = useQuery({
    queryKey: trainingQueryKeys.referencePreview(job.id),
    queryFn: () => getJobReferencePreview(job.id),
    enabled: Boolean(job.id && summary?.reference_data),
    retry: false,
  });

  // Local editable states
  const [editedCode, setEditedCode] = useState<string | null>(null);
  const [sourceCodeFile, setSourceCodeFile] = useState<File | null>(null);
  const [referenceDataFile, setReferenceDataFile] = useState<File | null>(null);
  const [stagedRemovals, setStagedRemovals] = useState<
    Set<"source_code" | "reference_data">
  >(new Set());

  const [conflictError, setConflictError] = useState<string | null>(null);
  const [unsavedConfirmOpen, setUnsavedConfirmOpen] = useState(false);

  // Active source code content
  const currentSourceContent = useMemo(() => {
    if (editedCode !== null) return editedCode;
    return summary?.source_code?.content ?? "";
  }, [editedCode, summary?.source_code?.content]);

  // Dirty detection
  const isSourceDirty = useMemo(() => {
    if (stagedRemovals.has("source_code")) return true;
    if (sourceCodeFile !== null) return true;
    if (
      editedCode !== null &&
      editedCode !== (summary?.source_code?.content ?? "")
    )
      return true;
    return false;
  }, [
    stagedRemovals,
    sourceCodeFile,
    editedCode,
    summary?.source_code?.content,
  ]);

  const isRefDirty = useMemo(() => {
    if (stagedRemovals.has("reference_data")) return true;
    if (referenceDataFile !== null) return true;
    return false;
  }, [stagedRemovals, referenceDataFile]);

  const isDirty = isSourceDirty || isRefDirty;

  // Save mutation
  const saveMutation = useMutation({
    mutationFn: async () => {
      if (!summary) return;
      let outgoingSourceFile: File | undefined;
      if (!stagedRemovals.has("source_code")) {
        const fileName =
          sourceCodeFile?.name || summary.source_code?.name || "main.py";
        if (editedCode !== null) {
          outgoingSourceFile = new File([editedCode], fileName, {
            type: "text/x-python",
          });
        } else if (sourceCodeFile) {
          outgoingSourceFile = sourceCodeFile;
        }
      }

      const removeList: string[] = [];
      if (stagedRemovals.has("source_code") && !outgoingSourceFile) {
        removeList.push("source_code");
      }
      if (stagedRemovals.has("reference_data") && !referenceDataFile) {
        removeList.push("reference_data");
      }

      return await patchModelOutput(job.id, {
        output_revision: summary.output_revision,
        source_code_file: outgoingSourceFile,
        reference_data_file: referenceDataFile || undefined,
        remove_assets: removeList.length > 0 ? removeList : undefined,
      });
    },
    onSuccess: (updated) => {
      if (!updated) return;
      setConflictError(null);
      setEditedCode(null);
      setSourceCodeFile(null);
      setReferenceDataFile(null);
      setStagedRemovals(new Set());
      queryClient.setQueryData(trainingQueryKeys.modelOutput(job.id), updated);
      void queryClient.invalidateQueries({
        queryKey: trainingQueryKeys.referencePreview(job.id),
      });
      void queryClient.invalidateQueries({
        queryKey: trainingQueryKeys.job(job.id),
      });
      toast.success(
        t("detail.artifactPage.saveSuccess", {
          revision: updated.output_revision,
        }),
      );
    },
    onError: (err: unknown) => {
      const status =
        err && typeof err === "object" && "response" in err
          ? (err as { response?: { status?: number } }).response?.status
          : undefined;
      if (status === 409) {
        setConflictError(
          getApiErrorMessage(err, t("detail.artifactPage.conflictDesc")),
        );
      } else {
        toast.error(
          getApiErrorMessage(err, t("detail.artifactPage.saveError")),
        );
      }
    },
  });

  const handleSourceFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    if (!file.name.toLowerCase().endsWith(".py")) {
      toast.error(t("detail.artifactPage.formatErrorSource"));
      e.target.value = "";
      return;
    }
    if (file.size > MAX_SOURCE_CODE_BYTES) {
      toast.error(t("detail.artifactPage.sizeErrorSource"));
      e.target.value = "";
      return;
    }

    setSourceCodeFile(file);
    setStagedRemovals((prev) => {
      const next = new Set(prev);
      next.delete("source_code");
      return next;
    });

    const reader = new FileReader();
    reader.onload = (event) => {
      const text = event.target?.result;
      if (typeof text === "string") {
        setEditedCode(text);
      }
    };
    reader.readAsText(file);
    e.target.value = "";
  };

  const handleRefFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    const lower = file.name.toLowerCase();
    if (!lower.endsWith(".csv")) {
      toast.error(t("detail.artifactPage.formatErrorRef"));
      e.target.value = "";
      return;
    }
    if (file.size > MAX_REFERENCE_DATA_BYTES) {
      toast.error(t("detail.artifactPage.sizeErrorRef"));
      e.target.value = "";
      return;
    }

    setReferenceDataFile(file);
    setStagedRemovals((prev) => {
      const next = new Set(prev);
      next.delete("reference_data");
      return next;
    });
    e.target.value = "";
  };

  const handleStageRemoveSource = () => {
    setStagedRemovals((prev) => new Set(prev).add("source_code"));
    setSourceCodeFile(null);
    setEditedCode(null);
  };

  const handleCancelSourceChanges = () => {
    setStagedRemovals((prev) => {
      const next = new Set(prev);
      next.delete("source_code");
      return next;
    });
    setSourceCodeFile(null);
    setEditedCode(null);
  };

  const handleStageRemoveRef = () => {
    setStagedRemovals((prev) => new Set(prev).add("reference_data"));
    setReferenceDataFile(null);
  };

  const handleCancelRefChanges = () => {
    setStagedRemovals((prev) => {
      const next = new Set(prev);
      next.delete("reference_data");
      return next;
    });
    setReferenceDataFile(null);
  };

  const handleReloadLatest = () => {
    setEditedCode(null);
    setSourceCodeFile(null);
    setReferenceDataFile(null);
    setStagedRemovals(new Set());
    setConflictError(null);
    void refetchSummary();
    void refetchPreview();
  };

  const proceedToBuild = () => {
    const build = job.registration_build;
    navigate(
      buildDeploymentPath({
        projectId: job.project_id,
        source: "training",
        jobId: job.id,
        buildId:
          build &&
          ["pending", "queued", "building", "ready"].includes(build.status)
            ? build.id
            : undefined,
      }),
    );
  };

  const handleBuildClick = () => {
    if (isDirty) {
      setUnsavedConfirmOpen(true);
    } else {
      proceedToBuild();
    }
  };

  if (loadingSummary) {
    return (
      <div className="flex h-72 items-center justify-center rounded-surface border border-border bg-surface">
        <RefreshCw className="h-6 w-6 animate-spin text-color-primary" />
      </div>
    );
  }

  if (summaryError || !summary) {
    return (
      <Callout
        variant="danger"
        title={t("detail.artifactPage.saveError")}
        description={getApiErrorMessage(
          summaryError,
          t("detail.artifactPage.saveError"),
        )}
      />
    );
  }

  const hasSourceCode =
    Boolean(summary.source_code) && !stagedRemovals.has("source_code");
  const hasRefData =
    Boolean(summary.reference_data) && !stagedRemovals.has("reference_data");

  return (
    <div className="space-y-6">
      {/* Top Header Card */}
      <div className="rounded-surface border border-border bg-surface p-6 shadow-sm">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <div className="flex items-center gap-3">
              <h2 className="text-style-section-title font-bold text-color-foreground">
                {t("detail.artifactPage.title")}
              </h2>
              <Badge variant="primary">
                {t("detail.artifactPage.revision", {
                  revision: summary.output_revision,
                })}
              </Badge>
              {isDirty && (
                <Badge variant="warning">
                  <span className="mr-1 inline-block h-1.5 w-1.5 rounded-full bg-warning animate-pulse" />
                  {t("detail.artifactPage.unsavedBadge")}
                </Badge>
              )}
            </div>
            <p className="mt-1 text-style-body text-color-muted-foreground">
              {t("detail.artifactPage.subtitle")}
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <Button
              variant="secondary"
              icon={<RefreshCw className="h-4 w-4" />}
              onClick={handleReloadLatest}
              title={t("detail.artifactPage.reload")}
            >
              {t("detail.artifactPage.reload")}
            </Button>
            <Button
              variant="primary"
              icon={<Save className="h-4 w-4" />}
              disabled={!isDirty || !summary.can_edit}
              loading={saveMutation.isPending}
              onClick={() => saveMutation.mutate()}
            >
              {saveMutation.isPending
                ? t("detail.artifactPage.saving")
                : t("detail.artifactPage.save")}
            </Button>
            <Button
              variant="secondary"
              icon={<Rocket className="h-4 w-4" />}
              disabled={job.status !== "completed" || !summary.can_build}
              onClick={handleBuildClick}
            >
              {t("detail.artifactPage.buildButton")}
            </Button>
          </div>
        </div>

        {/* Read only alert if not editable */}
        {!summary.can_edit && (
          <div className="mt-4">
            <Callout
              variant="info"
              title={t("detail.artifactPage.readOnlyNotice")}
              description={t("detail.artifactPage.readOnlyNotice")}
            />
          </div>
        )}

        {/* Conflict alert */}
        {conflictError && (
          <div className="mt-4">
            <Callout
              variant="danger"
              title={t("detail.artifactPage.conflictTitle")}
              description={conflictError}
            >
              <div className="mt-3">
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={handleReloadLatest}
                >
                  {t("detail.artifactPage.discardUnsaved")}
                </Button>
              </div>
            </Callout>
          </div>
        )}
      </div>

      {/* Grid: Model Artifact (Immutable) & Metrics */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* Model Artifact Card */}
        <div className="flex flex-col rounded-surface border border-border bg-surface p-6 shadow-sm">
          <div className="flex items-center justify-between border-b border-border pb-4">
            <div className="flex items-center gap-2">
              <Database className="h-5 w-5 text-color-primary" />
              <h3 className="text-style-body-strong font-semibold text-color-foreground">
                {t("detail.artifactPage.modelCardTitle")}
              </h3>
            </div>
            <Badge variant="neutral" className="flex items-center gap-1">
              <Lock className="h-3 w-3" />
              {t("detail.artifactPage.immutableBadge")}
            </Badge>
          </div>

          <div className="mt-4 flex-1 space-y-3">
            <p className="text-style-caption text-color-muted-foreground">
              {t("detail.artifactPage.immutableDesc")}
            </p>
            {summary.model_artifact ? (
              <div className="space-y-2 rounded-surface bg-muted/40 p-4 text-style-body-sm">
                <div className="flex justify-between">
                  <span className="text-color-muted-foreground">
                    {t("detail.artifactPage.relativePath")}
                  </span>
                  <span className="font-mono font-medium text-color-foreground">
                    {summary.model_artifact.relative_path}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-color-muted-foreground">
                    {t("detail.artifactPage.flavor")}:
                  </span>
                  <span className="font-medium text-color-foreground">
                    {summary.model_flavor}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-color-muted-foreground">
                    {t("detail.artifactPage.entryPoint")}:
                  </span>
                  <span className="font-mono text-color-foreground">
                    {summary.entry_point || "—"}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-color-muted-foreground">
                    {t("detail.artifactPage.fileSize")}
                  </span>
                  <span className="text-color-foreground">
                    {formatBytes(summary.model_artifact.size_bytes)}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-color-muted-foreground">
                    {t("detail.artifactPage.checksumLabel")}
                  </span>
                  <span className="max-w-50 truncate font-mono text-style-caption text-color-muted-foreground">
                    {summary.model_artifact.checksum || "—"}
                  </span>
                </div>
              </div>
            ) : (
              <div className="flex h-32 items-center justify-center text-style-caption text-color-muted-foreground">
                {t("detail.artifactPage.notReady")}
              </div>
            )}
          </div>
        </div>

        {/* Metrics & Parameters Card */}
        <div className="flex flex-col rounded-surface border border-border bg-surface p-6 shadow-sm">
          <div className="flex items-center gap-2 border-b border-border pb-4">
            <BarChart2 className="h-5 w-5 text-color-primary" />
            <h3 className="text-style-body-strong font-semibold text-color-foreground">
              {t("detail.artifactPage.metricsCardTitle")}
            </h3>
          </div>

          <div className="mt-4 flex-1 overflow-y-auto space-y-4 max-h-64">
            {Object.keys(summary.metrics).length === 0 &&
            Object.keys(summary.params).length === 0 ? (
              <div className="flex h-32 items-center justify-center text-style-caption text-color-muted-foreground">
                {t("detail.artifactPage.noMetrics")}
              </div>
            ) : (
              <>
                {Object.keys(summary.metrics).length > 0 && (
                  <div>
                    <h4 className="mb-2 text-style-caption-strong uppercase text-color-muted-foreground">
                      {t("detail.artifactPage.metricsLabel")}
                    </h4>
                    <div className="grid grid-cols-2 gap-2">
                      {Object.entries(summary.metrics).map(([key, val]) => (
                        <div
                          key={key}
                          className="rounded-surface bg-muted/40 p-2 text-style-caption"
                        >
                          <span className="text-color-muted-foreground">
                            {key}:{" "}
                          </span>
                          <span className="font-semibold text-color-foreground">
                            {typeof val === "number"
                              ? val.toFixed(4)
                              : String(val)}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {Object.keys(summary.params).length > 0 && (
                  <div>
                    <h4 className="mb-2 text-style-caption-strong uppercase text-color-muted-foreground">
                      {t("detail.artifactPage.paramsLabel")}
                    </h4>
                    <div className="grid grid-cols-2 gap-2">
                      {Object.entries(summary.params).map(([key, val]) => (
                        <div
                          key={key}
                          className="rounded-surface bg-muted/40 p-2 text-style-caption"
                        >
                          <span className="text-color-muted-foreground">
                            {key}:{" "}
                          </span>
                          <span className="font-semibold text-color-foreground">
                            {String(val)}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </>
            )}
          </div>
        </div>
      </div>

      {/* Supplemental Source Code Section */}
      <div className="rounded-surface border border-border bg-surface p-6 shadow-sm">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between border-b border-border pb-4">
          <div>
            <div className="flex items-center gap-2">
              <Code2 className="h-5 w-5 text-color-primary" />
              <h3 className="text-style-body-strong font-semibold text-color-foreground">
                {t("detail.artifactPage.sourceCardTitle")}
              </h3>
              {isSourceDirty && (
                <Badge variant="warning">{t("detail.artifactPage.unsaved")}</Badge>
              )}
            </div>
            <p className="mt-1 text-style-caption text-color-muted-foreground">
              {t("detail.artifactPage.sourceCardDesc")}
            </p>
          </div>

          <div className="flex items-center gap-2">
            <input
              type="file"
              ref={sourceFileInputRef}
              accept=".py"
              className="hidden"
              onChange={handleSourceFileChange}
            />
            {summary.can_edit && (
              <>
                <Button
                  size="sm"
                  variant="secondary"
                  icon={<Upload className="h-4 w-4" />}
                  onClick={() => sourceFileInputRef.current?.click()}
                >
                  {hasSourceCode || sourceCodeFile
                    ? t("detail.artifactPage.replaceSource")
                    : t("detail.artifactPage.uploadSource")}
                </Button>
                {(hasSourceCode || sourceCodeFile) && (
                  <Button
                    size="sm"
                    variant="danger"
                    icon={<Trash2 className="h-4 w-4" />}
                    onClick={handleStageRemoveSource}
                  >
                    {t("detail.artifactPage.removeSource")}
                  </Button>
                )}
              </>
            )}
          </div>
        </div>

        {/* Staged indicators */}
        {stagedRemovals.has("source_code") && (
          <div className="mt-3 flex items-center justify-between rounded-surface bg-danger-subtle px-4 py-2 text-style-caption text-color-danger">
            <span className="flex items-center gap-2">
              <AlertCircle className="h-4 w-4" />
              {t("detail.artifactPage.stagedRemove")}
            </span>
            <Button
              size="sm"
              variant="ghost"
              onClick={handleCancelSourceChanges}
            >
              {t("detail.artifactPage.cancelStage")}
            </Button>
          </div>
        )}

        {sourceCodeFile && (
          <div className="mt-3 flex items-center justify-between rounded-surface bg-success-subtle px-4 py-2 text-style-caption text-color-success">
            <span className="flex items-center gap-2">
              <CheckCircle2 className="h-4 w-4" />
              {t("detail.artifactPage.stagedUpload", {
                name: sourceCodeFile.name,
                size: formatBytes(sourceCodeFile.size),
              })}
            </span>
            <Button
              size="sm"
              variant="ghost"
              onClick={handleCancelSourceChanges}
            >
              {t("detail.artifactPage.cancelStage")}
            </Button>
          </div>
        )}

        {/* Content / Editor */}
        <div className="mt-4">
          {!hasSourceCode && !sourceCodeFile ? (
            <div
              onClick={() =>
                summary.can_edit && sourceFileInputRef.current?.click()
              }
              className={`flex h-48 flex-col items-center justify-center rounded-surface border-2 border-dashed border-border p-6 text-center transition-colors ${
                summary.can_edit
                  ? "cursor-pointer hover:border-primary hover:bg-muted/40"
                  : ""
              }`}
            >
              <FileCode className="h-10 w-10 text-color-muted-foreground mb-2" />
              <p className="text-style-body font-medium text-color-foreground">
                {t("detail.artifactPage.sourceEmpty")}
              </p>
              <p className="mt-1 text-style-caption text-color-muted-foreground">
                {t("detail.artifactPage.limitHint")}
              </p>
            </div>
          ) : (
            <div className="overflow-hidden rounded-surface border border-border">
              <div className="flex items-center justify-between bg-muted px-4 py-2 text-style-caption text-color-muted-foreground border-b border-border">
                <span className="font-mono">
                  {sourceCodeFile?.name ||
                    summary.source_code?.name ||
                    summary.entry_point ||
                    "main.py"}
                </span>
                <span>
                  {formatBytes(
                    sourceCodeFile?.size ?? summary.source_code?.size_bytes,
                  )}
                </span>
              </div>
              <div className="h-80 bg-surface">
                <CodeViewer
                  height="100%"
                  language="python"
                  theme={resolvedTheme === "dark" ? "vs-dark" : "vs"}
                  value={currentSourceContent}
                  onChange={(val) => {
                    if (summary.can_edit) {
                      setEditedCode(val ?? "");
                    }
                  }}
                  options={{
                    minimap: { enabled: false },
                    // typography-ignore: Monaco requires a numeric pixel value.
                    fontSize: 13,
                    readOnly: !summary.can_edit,
                    wordWrap: "on",
                    scrollBeyondLastLine: false,
                  }}
                />
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Supplemental Reference Dataset Section */}
      <div className="rounded-surface border border-border bg-surface p-6 shadow-sm">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between border-b border-border pb-4">
          <div>
            <div className="flex items-center gap-2">
              <FileSpreadsheet className="h-5 w-5 text-color-primary" />
              <h3 className="text-style-body-strong font-semibold text-color-foreground">
                {t("detail.artifactPage.refCardTitle")}
              </h3>
              {isRefDirty && <Badge variant="warning">{t("detail.artifactPage.unsaved")}</Badge>}
            </div>
            <p className="mt-1 text-style-caption text-color-muted-foreground">
              {t("detail.artifactPage.refCardDesc")}
            </p>
          </div>

          <div className="flex items-center gap-2">
            <input
              type="file"
              ref={refFileInputRef}
              accept=".csv"
              className="hidden"
              onChange={handleRefFileChange}
            />
            {summary.can_edit && (
              <>
                <Button
                  size="sm"
                  variant="secondary"
                  icon={<Upload className="h-4 w-4" />}
                  onClick={() => refFileInputRef.current?.click()}
                >
                  {hasRefData || referenceDataFile
                    ? t("detail.artifactPage.replaceRef")
                    : t("detail.artifactPage.uploadRef")}
                </Button>
                {(hasRefData || referenceDataFile) && (
                  <Button
                    size="sm"
                    variant="danger"
                    icon={<Trash2 className="h-4 w-4" />}
                    onClick={handleStageRemoveRef}
                  >
                    {t("detail.artifactPage.removeRef")}
                  </Button>
                )}
              </>
            )}
          </div>
        </div>

        {/* Staged indicators */}
        {stagedRemovals.has("reference_data") && (
          <div className="mt-3 flex items-center justify-between rounded-surface bg-danger-subtle px-4 py-2 text-style-caption text-color-danger">
            <span className="flex items-center gap-2">
              <AlertCircle className="h-4 w-4" />
              {t("detail.artifactPage.stagedRemove")}
            </span>
            <Button size="sm" variant="ghost" onClick={handleCancelRefChanges}>
              {t("detail.artifactPage.cancelStage")}
            </Button>
          </div>
        )}

        {referenceDataFile && (
          <div className="mt-3 flex items-center justify-between rounded-surface bg-success-subtle px-4 py-2 text-style-caption text-color-success">
            <span className="flex items-center gap-2">
              <CheckCircle2 className="h-4 w-4" />
              {t("detail.artifactPage.stagedUpload", {
                name: referenceDataFile.name,
                size: formatBytes(referenceDataFile.size),
              })}
            </span>
            <Button size="sm" variant="ghost" onClick={handleCancelRefChanges}>
              {t("detail.artifactPage.cancelStage")}
            </Button>
          </div>
        )}

        {/* Content / Preview Table */}
        <div className="mt-4">
          {!hasRefData && !referenceDataFile ? (
            <div
              onClick={() =>
                summary.can_edit && refFileInputRef.current?.click()
              }
              className={`flex h-48 flex-col items-center justify-center rounded-surface border-2 border-dashed border-border p-6 text-center transition-colors ${
                summary.can_edit
                  ? "cursor-pointer hover:border-primary hover:bg-muted/40"
                  : ""
              }`}
            >
              <FileSpreadsheet className="h-10 w-10 text-color-muted-foreground mb-2" />
              <p className="text-style-body font-medium text-color-foreground">
                {t("detail.artifactPage.refEmpty")}
              </p>
              <p className="mt-1 text-style-caption text-color-muted-foreground">
                {t("detail.artifactPage.limitHint")}
              </p>
            </div>
          ) : referenceDataFile ? (
            <div className="rounded-surface bg-muted/40 p-4 text-center text-style-body-sm text-color-muted-foreground">
              {t("detail.artifactPage.stagedRefNotice", {
                name: referenceDataFile.name,
              })}
            </div>
          ) : loadingPreview ? (
            <div className="flex h-48 items-center justify-center rounded-surface border border-border bg-surface">
              <RefreshCw className="h-6 w-6 animate-spin text-color-primary" />
            </div>
          ) : previewError || !refPreview ? (
            <div className="rounded-surface border border-border bg-surface p-4 text-center text-style-caption text-color-muted-foreground">
              {getApiErrorMessage(
                previewError,
                t("detail.artifactPage.previewEmpty"),
              )}
            </div>
          ) : (
            <div className="overflow-hidden rounded-surface border border-border">
              <div className="flex items-center justify-between bg-muted px-4 py-2 text-style-caption text-color-muted-foreground border-b border-border">
                <span className="font-mono">
                  {refPreview.filename} ({refPreview.format.toUpperCase()})
                </span>
                <span>
                  {t("detail.artifactPage.previewRows", {
                    count: refPreview.rows.length,
                  })}{" "}
                  · {refPreview.total_rows} {t("detail.artifactPage.totalRows")}
                </span>
              </div>
              <div className="max-h-72 overflow-auto">
                <table className="min-w-full divide-y divide-border border-collapse text-left text-style-caption">
                  <thead className="sticky top-0 bg-muted/80 backdrop-blur z-10">
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
                                {t("detail.artifactPage.nullValue")}
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
        </div>
      </div>

      {/* Bottom Actions: Download and Delete */}
      <div className="flex flex-wrap items-center justify-between gap-4 border-t border-border pt-6">
        <div className="flex items-center gap-3">
          <Button
            variant="secondary"
            icon={<Download className="h-4 w-4" />}
            disabled={!job.output_available}
            loading={downloadingOutput}
            onClick={downloadOutput}
          >
            {t("detail.artifactPage.download")}
          </Button>
          <Button
            variant="danger"
            icon={<Trash2 className="h-4 w-4" />}
            disabled={!job.output_available}
            onClick={requestDeleteOutputs}
          >
            {t("detail.artifactPage.delete")}
          </Button>
        </div>

        <div className="flex items-center gap-3">
          <Button
            variant="primary"
            icon={<Rocket className="h-4 w-4" />}
            disabled={job.status !== "completed" || !summary.can_build}
            onClick={handleBuildClick}
          >
            {t("detail.artifactPage.buildButton")}
          </Button>
        </div>
      </div>

      {/* Unsaved Changes Confirmation Dialog */}
      <ConfirmDialog
        open={unsavedConfirmOpen}
        title={t("detail.artifactPage.unsavedConfirmTitle")}
        description={t("detail.artifactPage.unsavedConfirmDesc")}
        confirmText={t("detail.artifactPage.buildAnyway")}
        tone="default"
        onConfirm={() => {
          setUnsavedConfirmOpen(false);
          proceedToBuild();
        }}
        onCancel={() => setUnsavedConfirmOpen(false)}
      />
    </div>
  );
}
