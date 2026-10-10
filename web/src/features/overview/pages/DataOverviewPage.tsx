import { OverviewArtifactDropzone } from "@/features/overview/components/OverviewArtifactDropzone";
import {
  removePreviewAsset,
  uploadPreviewSingleAsset,
  type PreviewAsset,
} from "@/features/projects/api/previewApi";
import { getApiErrorMessage } from "@/shared/api/errors";
import { Badge } from "@/shared/components/Badge";
import { Button } from "@/shared/components/Button";
import { ConfirmDialog } from "@/shared/components/ConfirmDialog";
import { DataViewer } from "@/shared/components/DataViewer";
import { Loading } from "@/shared/components/Loading";
import { Placeholder } from "@/shared/components/Placeholder";
import { toast } from "@/shared/types/toastStore";
import {
  Download,
  GitBranch,
  Lock,
  RotateCcw,
  Save,
  Table as TableIcon,
  Trash2,
} from "lucide-react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

export interface DataOverviewPageProps {
  modelId: string;
  effectiveVersionId?: string;
  isPreview: boolean;
  referenceDataName?: string;
  reference: {
    data?: string;
    isLoading: boolean;
    isError: boolean;
  };
  previewReference: {
    asset?: PreviewAsset;
    data?: string;
    isLoading: boolean;
    isError: boolean;
  };
  onUploadSuccess: () => void | Promise<void>;
}

export function DataOverviewPage({
  modelId,
  effectiveVersionId,
  isPreview,
  referenceDataName,
  reference,
  previewReference,
  onUploadSuccess,
}: DataOverviewPageProps) {
  const { t } = useTranslation("overview");
  const navigate = useNavigate();
  const [viewerContainerEl, setViewerContainerEl] = useState<HTMLDivElement | null>(null);
  const [viewerHeight, setViewerHeight] = useState<number>(450);

  const initialData = isPreview
    ? (previewReference.data || "")
    : (reference.data || "");
  const [editedCsv, setEditedCsv] = useState<string | null>(null);
  const csvContent = editedCsv ?? initialData;
  const [revertKey, setRevertKey] = useState(0);
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);

  const fileName = isPreview
    ? (previewReference.asset?.name || "reference_data.csv")
    : (referenceDataName || "reference_data.csv");

  const isDirty = isPreview && editedCsv !== null && editedCsv !== initialData;

  const handleDiscard = () => {
    setEditedCsv(null);
    setRevertKey((k) => k + 1);
  };

  const handleDownload = () => {
    const content = isPreview ? csvContent : (reference.data || "");
    if (!content) return;
    const blob = new Blob([content], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.setAttribute("download", fileName);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  };

  const handleSave = async () => {
    if (!isPreview || !isDirty || saving) return;
    try {
      setSaving(true);
      const file = new File([csvContent], fileName, {
        type: "text/csv",
      });
      await uploadPreviewSingleAsset(modelId, "reference_data", file);
      toast.success(t("workflow.fileSaved"));
      setEditedCsv(null);
      await onUploadSuccess();
    } catch (err) {
      toast.error(getApiErrorMessage(err, t("workflow.fileSaveFailed")));
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async () => {
    if (!isPreview) return;
    try {
      setDeleting(true);
      await removePreviewAsset(modelId, "reference_data");
      toast.success(t("workflow.fileDeleted"));
      setDeleteOpen(false);
      setEditedCsv(null);
      await onUploadSuccess();
    } catch (err) {
      toast.error(getApiErrorMessage(err, t("workflow.fileDeleteFailed")));
    } finally {
      setDeleting(false);
    }
  };

  useEffect(() => {
    if (!viewerContainerEl) return;

    const updateHeight = () => {
      const rect = viewerContainerEl.getBoundingClientRect();
      const mainEl = document.getElementById("main-content");
      const mainPaddingBottom = mainEl
        ? parseFloat(window.getComputedStyle(mainEl).paddingBottom) || 24
        : 24;
      const sectionEl = viewerContainerEl.closest("section");
      const sectionPaddingBottom = sectionEl
        ? parseFloat(window.getComputedStyle(sectionEl).paddingBottom) || 24
        : 24;
      const bottomSpacing = mainPaddingBottom + sectionPaddingBottom + 4;
      const available = window.innerHeight - rect.top - bottomSpacing;
      setViewerHeight(Math.max(250, Math.floor(available)));
    };

    updateHeight();
    window.addEventListener("resize", updateHeight);

    const mainEl = document.getElementById("main-content");
    let observer: ResizeObserver | null = null;
    if (mainEl && typeof ResizeObserver !== "undefined") {
      observer = new ResizeObserver(() => {
        updateHeight();
      });
      observer.observe(mainEl);
    }

    return () => {
      window.removeEventListener("resize", updateHeight);
      observer?.disconnect();
    };
  }, [viewerContainerEl]);

  if (isPreview ? previewReference.isLoading : reference.isLoading) {
    return (
      <Placeholder role="tabpanel" className="flex-1 min-h-105">
        <Loading size="lg" text={t("workflow.loadingData")} />
      </Placeholder>
    );
  }

  const hasData = isPreview
    ? Boolean(previewReference.asset && previewReference.data)
    : Boolean(reference.data);

  if ((isPreview ? previewReference.isError : reference.isError) && !hasData) {
    return (
      <Placeholder role="tabpanel" className="flex-1 min-h-105">
        <p role="alert" className="text-style-body text-color-danger">
          {t("workflow.failed")}
        </p>
      </Placeholder>
    );
  }

  if (!isPreview && !hasData) {
    return (
      <Placeholder
        role="tabpanel"
        className="flex-1 min-h-105"
        icon={<TableIcon className="h-6 w-6 text-color-primary" />}
        title={t("workflow.noRunningDataTitle")}
        description={t("workflow.noRunningDataDesc")}
        action={
          effectiveVersionId ? (
            <Button
              variant="secondary"
              icon={<GitBranch className="h-4 w-4" />}
              onClick={() =>
                navigate(
                  `/dashboard/projects/${modelId}/evolution?versionId=${effectiveVersionId}&tab=details`,
                )
              }
            >
              {t("workflow.openInEvolution")}
            </Button>
          ) : undefined
        }
      />
    );
  }

  return (
    <section
      role="tabpanel"
      className="flex flex-1 flex-col space-y-5 rounded-surface border border-border bg-surface p-6"
    >
      {isPreview ? (
        hasData ? (
          <div
            ref={setViewerContainerEl}
            style={{ height: `${viewerHeight}px` }}
            className="w-full min-h-0 flex-1 overflow-hidden"
          >
            <DataViewer
              key={revertKey}
              title={fileName}
              badge={
                <>
                  <Badge variant="info">
                    {t("workflow.previewBadge")}
                  </Badge>
                  {isDirty && (
                    <Badge variant="warning">
                      {t("workflow.unsavedBadge")}
                    </Badge>
                  )}
                </>
              }
              actions={
                <>
                  <Button
                    variant="primary"
                    size="md"
                    onClick={handleSave}
                    disabled={!isDirty || saving}
                    loading={saving}
                    icon={<Save className="h-4 w-4" />}
                  >
                    {saving ? t("workflow.savingFile") : t("workflow.saveFile")}
                  </Button>
                  {isDirty && (
                    <Button
                      variant="secondary"
                      size="icon"
                      onClick={handleDiscard}
                      disabled={saving}
                      icon={<RotateCcw className="h-4 w-4" />}
                      title={t("workflow.discardChanges")}
                      aria-label={t("workflow.discardChanges")}
                    >
                    </Button>
                  )}
                  <Button
                    size="icon"
                    variant="secondary"
                    onClick={handleDownload}
                    disabled={saving || deleting}
                    icon={<Download className="h-4 w-4" />}
                    title={t("workflow.downloadFile")}
                    aria-label={t("workflow.downloadFile")}
                  />
                  <Button
                    size="icon"
                    variant="secondary"
                    onClick={() => setDeleteOpen(true)}
                    disabled={saving || deleting}
                    icon={<Trash2 className="h-4 w-4" />}
                    title={t("workflow.deleteFile")}
                    aria-label={t("workflow.deleteFile")}
                  />
                </>
              }
              initialCsvText={initialData}
              onChange={(newCsv) => setEditedCsv(newCsv)}
              readOnly={false}
            />
          </div>
        ) : (
          <OverviewArtifactDropzone
            projectId={modelId}
            kind="reference_data"
            onUploadSuccess={onUploadSuccess}
          />
        )
      ) : (
        <div
          ref={setViewerContainerEl}
          style={{ height: `${viewerHeight}px` }}
          className="w-full min-h-0 flex-1 overflow-hidden"
        >
          <DataViewer
            title={fileName}
            badge={
              <Badge variant="neutral">
                <Lock className="h-3 w-3 mr-1 inline" />
                {t("workflow.immutableBadge")}
              </Badge>
            }
            actions={
              <>
                <Button
                  size="icon"
                  variant="secondary"
                  onClick={handleDownload}
                  icon={<Download className="h-4 w-4" />}
                  title={t("workflow.downloadFile")}
                  aria-label={t("workflow.downloadFile")}
                />
                <span className="text-style-caption text-color-muted-foreground">
                  {t("workflow.immutableNotice")}
                </span>
              </>
            }
            initialCsvText={reference.data || ""}
            readOnly={true}
          />
        </div>
      )}

      <ConfirmDialog
        open={deleteOpen}
        title={t("workflow.deleteDataConfirmTitle")}
        description={t("workflow.deleteDataConfirmDesc")}
        tone="danger"
        loading={deleting}
        onConfirm={handleDelete}
        onCancel={() => setDeleteOpen(false)}
      />
    </section>
  );
}

export default DataOverviewPage;
