import {
  AlertTriangle,
  CheckCircle,
  Clock,
  Info,
  Loader2,
  UploadCloud,
  XCircle,
} from "lucide-react";
import { useTranslation } from "react-i18next";

import { MetadataRow } from "@/features/training/components/TrainingOverviewSections";
import { useTrainingJobDetailContext } from "@/features/training/trainingJobDetailContext";
import { computeElapsed, formatDuration } from "@/shared/lib/formatDuration";
import { PageBody } from "@/shared/components/PageBody";
import { ProgressLine, type ProgressLineStep } from "@/shared/components/ProgressLine";

export default function TrainingJobOverviewPage() {
  const { t } = useTranslation("training");
  const { job, statusLabels } = useTrainingJobDetailContext();

  const isCompleted = job.status === "completed";
  const isFailed = job.status === "failed";
  const isCancelled = job.status === "cancelled";
  const isRunning = job.status === "running";
  const isUploading = job.status === "uploading";
  const hasStarted = Boolean(job.started_at);

  let submittedState: "pending" | "active" | "completed" = "pending";
  if (isUploading) submittedState = "active";
  else if (isRunning || isCompleted || isFailed || isCancelled)
    submittedState = "completed";

  let runningState: "pending" | "active" | "completed" | "skipped" = "pending";
  if (isRunning) runningState = "active";
  else if (isCompleted) runningState = "completed";
  else if (isFailed || isCancelled)
    runningState = hasStarted ? "completed" : "skipped";

  let finalLabel = t("detail.milestones.completed");
  let finalState: "pending" | "completed" | "failed" | "cancelled" = "pending";
  if (isCompleted) finalState = "completed";
  else if (isFailed) {
    finalLabel = t("detail.milestones.failed");
    finalState = "failed";
  } else if (isCancelled) {
    finalLabel = t("detail.milestones.cancelled");
    finalState = "cancelled";
  }

  const formatTime = (iso?: string | null) =>
    iso ? new Date(iso).toLocaleString() : t("detail.milestones.unavailable");
  const formatDurationDiff = (start?: string | null, end?: string | null) => {
    const elapsed = computeElapsed(start, end ?? undefined);
    return elapsed != null ? formatDuration(elapsed) : undefined;
  };
  const milestones: ProgressLineStep[] = [
    {
      id: "created",
      label: t("detail.milestones.created"),
      state: "completed" as const,
      icon: Clock,
      timestamp: formatTime(job.created_at),
      helper: undefined,
    },
    {
      id: "submitted",
      label: t("detail.milestones.submitted"),
      state: submittedState,
      icon: UploadCloud,
      timestamp:
        submittedState === "completed" || submittedState === "active"
          ? formatTime(job.updated_at)
          : t("detail.milestones.pending"),
      helper: undefined,
    },
    {
      id: "running",
      label: t("detail.milestones.running"),
      state: runningState,
      icon: Loader2,
      timestamp:
        runningState === "completed" || runningState === "active"
          ? formatTime(job.started_at)
          : runningState === "skipped"
            ? t("detail.milestones.skipped")
            : t("detail.milestones.pending"),
      helper:
        hasStarted && job.created_at
          ? t("detail.milestones.startedAfter", {
              duration: formatDurationDiff(job.created_at, job.started_at),
            })
          : undefined,
    },
    {
      id: "final",
      label: finalLabel,
      state: finalState,
      icon:
        finalState === "failed" || finalState === "cancelled"
          ? XCircle
          : CheckCircle,
      timestamp:
        finalState !== "pending"
          ? formatTime(job.completed_at)
          : t("detail.milestones.pending"),
      helper:
        job.completed_at && job.started_at
          ? t("detail.milestones.finishedIn", {
              duration: formatDurationDiff(job.started_at, job.completed_at),
            })
          : undefined,
    },
  ];

  return (
    <div className="space-y-6">
      <PageBody>
        <div className="p-6 sm:p-8">
          <div className="w-full overflow-x-auto pb-4">
            <ProgressLine steps={milestones} />
          </div>
        </div>
      </PageBody>

      {job.status === "failed" && (
        <div className="rounded-surface border border-danger/20 bg-danger-subtle p-5">
          <h4 className="mb-2 flex items-center gap-2 text-style-heading text-color-danger">
            <AlertTriangle className="h-5 w-5" />
            {t("detail.overview.failedTitle")}
          </h4>
          <p className="mb-3 text-style-body-strong text-color-danger">
            {job.stop_reason || t("detail.overview.failedFallback")}
          </p>
          {job.error_message && (
            <div className="overflow-x-auto rounded-surface border border-danger/20 bg-surface p-4">
              <code className="wrap-break-words whitespace-pre-wrap font-mono text-style-code-sm text-color-danger">
                {job.error_message}
              </code>
            </div>
          )}
        </div>
      )}

      {job.status === "cancelled" && (
        <div className="rounded-surface border border-warning/20 bg-warning-subtle p-5">
          <h4 className="mb-2 flex items-center gap-2 text-style-heading text-color-warning">
            <AlertTriangle className="h-5 w-5" />
            {t("detail.overview.cancelledTitle")}
          </h4>
          <p className="text-style-body-strong text-color-warning">
            {job.stop_reason || t("detail.overview.cancelledFallback")}
          </p>
        </div>
      )}

      <PageBody
        title={
          <div className="flex items-center gap-2">
            <Info className="h-5 w-5" />
            <h3 className="text-style-heading">{t("detail.overview.metadataTitle")}</h3>
          </div>
        }
      >
        <div className="grid grid-cols-1 gap-x-8 gap-y-6 p-6 md:grid-cols-2">
          <MetadataRow label={t("detail.overview.internalJobId")} value={String(job.id)} />
          <MetadataRow
            label={t("detail.overview.externalJobId")}
            value={job.external_job_id || job.sagemaker_job_name || "-"}
          />
          <MetadataRow label={t("detail.overview.modelName")} value={job.name} />
          <MetadataRow label={t("detail.overview.modelVersion")} value={job.model_version} />
          <MetadataRow label={t("detail.overview.backend")} value={job.backend || t("statuses.unknown", { ns: "common" })} />
          <MetadataRow label={t("detail.overview.status")} value={statusLabels[job.status]} />
          <MetadataRow
            label={t("detail.overview.createdAt")}
            value={new Date(job.created_at).toLocaleString()}
          />
          <MetadataRow
            label={t("detail.overview.updatedAt")}
            value={new Date(job.updated_at).toLocaleString()}
          />
          <MetadataRow
            label={t("detail.overview.startedAt")}
            value={
              job.started_at ? new Date(job.started_at).toLocaleString() : "-"
            }
          />
          <MetadataRow
            label={t("detail.overview.completedAt")}
            value={
              job.completed_at
                ? new Date(job.completed_at).toLocaleString()
                : "-"
            }
          />
        </div>
      </PageBody>
    </div>
  );
}
