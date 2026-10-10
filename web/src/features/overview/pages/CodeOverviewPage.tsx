import { OverviewArtifactDropzone } from "@/features/overview/components/OverviewArtifactDropzone";
import {
  removePreviewAsset,
  uploadPreviewSingleAsset,
  type PreviewAsset,
} from "@/features/projects/api/previewApi";
import { getApiErrorMessage } from "@/shared/api/errors";
import { Badge } from "@/shared/components/Badge";
import { Button } from "@/shared/components/Button";
import { CodeViewer } from "@/shared/components/CodeViewer";
import { ConfirmDialog } from "@/shared/components/ConfirmDialog";
import { Loading } from "@/shared/components/Loading";
import { Placeholder } from "@/shared/components/Placeholder";
import { toast } from "@/shared/types/toastStore";
import {
  Download,
  Code,
  GitBranch,
  Lock,
  RotateCcw,
  Save,
  Trash2,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

export interface CodeOverviewPageProps {
  modelId: string;
  effectiveVersionId?: string;
  isPreview: boolean;
  source: {
    data?: string;
    isLoading: boolean;
    isError: boolean;
  };
  previewSource: {
    asset?: PreviewAsset;
    data?: string;
    isLoading: boolean;
    isError: boolean;
  };
  theme?: string;
  onUploadSuccess: () => void | Promise<void>;
}

export function CodeOverviewPage({
  modelId,
  effectiveVersionId,
  isPreview,
  source,
  previewSource,
  theme = "light",
  onUploadSuccess,
}: CodeOverviewPageProps) {
  const { t } = useTranslation("overview");
  const navigate = useNavigate();
  const [editorContainerEl, setEditorContainerEl] = useState<HTMLDivElement | null>(null);
  const [editorHeight, setEditorHeight] = useState<number>(450);

  const initialCode = isPreview ? (previewSource.data || "") : (source.data || "");
  const [editedCode, setEditedCode] = useState<string | null>(null);
  const codeContent = editedCode ?? initialCode;
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);

  const fileName = isPreview
    ? (previewSource.asset?.name || "source_code.py")
    : "source_code.py";

  const isDirty = isPreview && editedCode !== null && editedCode !== initialCode;

  const handleDiscard = () => {
    setEditedCode(null);
  };

  const handleDownload = () => {
    const content = isPreview ? codeContent : (source.data || "");
    if (!content) return;
    const blob = new Blob([content], { type: "text/x-python;charset=utf-8;" });
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
      const file = new File([codeContent], fileName, {
        type: "text/x-python",
      });
      await uploadPreviewSingleAsset(modelId, "source_code", file);
      toast.success(t("workflow.fileSaved"));
      setEditedCode(null);
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
      await removePreviewAsset(modelId, "source_code");
      toast.success(t("workflow.fileDeleted"));
      setDeleteOpen(false);
      setEditedCode(null);
      await onUploadSuccess();
    } catch (err) {
      toast.error(getApiErrorMessage(err, t("workflow.fileDeleteFailed")));
    } finally {
      setDeleting(false);
    }
  };

  const saveRef = useRef(handleSave);
  useEffect(() => {
    saveRef.current = handleSave;
  });

  useEffect(() => {
    if (!editorContainerEl) return;

    const updateHeight = () => {
      const rect = editorContainerEl.getBoundingClientRect();
      const mainEl = document.getElementById("main-content");
      const mainPaddingBottom = mainEl
        ? parseFloat(window.getComputedStyle(mainEl).paddingBottom) || 24
        : 24;
      const sectionEl = editorContainerEl.closest("section");
      const sectionPaddingBottom = sectionEl
        ? parseFloat(window.getComputedStyle(sectionEl).paddingBottom) || 24
        : 24;
      const bottomSpacing = mainPaddingBottom + sectionPaddingBottom + 4;
      const available = window.innerHeight - rect.top - bottomSpacing;
      setEditorHeight(Math.max(250, Math.floor(available)));
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
  }, [editorContainerEl]);

  if (isPreview ? previewSource.isLoading : source.isLoading) {
    return (
      <Placeholder role="tabpanel" className="flex-1 min-h-105">
        <Loading size="lg" text={t("workflow.loadingCode")} />
      </Placeholder>
    );
  }

  const hasCode = isPreview
    ? Boolean(previewSource.asset && previewSource.data)
    : Boolean(source.data);

  if ((isPreview ? previewSource.isError : source.isError) && !hasCode) {
    return (
      <Placeholder role="tabpanel" className="flex-1 min-h-105">
        <p role="alert" className="text-style-body text-color-danger">
          {t("workflow.failed")}
        </p>
      </Placeholder>
    );
  }

  if (!isPreview && !hasCode) {
    return (
      <Placeholder
        role="tabpanel"
        className="flex-1 min-h-105"
        icon={<Code className="h-6 w-6 text-color-primary" />}
        title={t("workflow.noRunningCodeTitle")}
        description={t("workflow.noRunningCodeDesc")}
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
        hasCode ? (
          <div
            ref={setEditorContainerEl}
            style={{ height: `${editorHeight}px` }}
            className="w-full min-h-0 flex-1 overflow-hidden"
          >
            <CodeViewer
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
                      size="icon"
                      variant="secondary"  
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
              language="python"
              theme={theme === "dark" ? "vs-dark" : "light"}
              value={codeContent}
              onChange={(val) => setEditedCode(val ?? "")}
              onMount={(editor, monaco) => {
                editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyS, () => {
                  saveRef.current?.();
                });
              }}
              options={{
                readOnly: false,
                minimap: { enabled: false },
                scrollBeyondLastLine: false,
                automaticLayout: true,
              }}
            />
          </div>
        ) : (
          <OverviewArtifactDropzone
            projectId={modelId}
            kind="source_code"
            onUploadSuccess={onUploadSuccess}
          />
        )
      ) : (
        <div
          ref={setEditorContainerEl}
          style={{ height: `${editorHeight}px` }}
          className="w-full min-h-0 flex-1 overflow-hidden"
        >
          <CodeViewer
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
            language="python"
            theme={theme === "dark" ? "vs-dark" : "light"}
            value={source.data}
            options={{
              readOnly: true,
              minimap: { enabled: false },
              scrollBeyondLastLine: false,
              automaticLayout: true,
            }}
          />
        </div>
      )}

      <ConfirmDialog
        open={deleteOpen}
        title={t("workflow.deleteSourceConfirmTitle")}
        description={t("workflow.deleteSourceConfirmDesc")}
        tone="danger"
        loading={deleting}
        onConfirm={handleDelete}
        onCancel={() => setDeleteOpen(false)}
      />
    </section>
  );
}

export default CodeOverviewPage;
