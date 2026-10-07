import { OverviewArtifactDropzone } from "@/features/overview/components/OverviewArtifactDropzone";
import type { PreviewAsset } from "@/features/projects/api/previewApi";
import { CodeViewer } from "@/shared/components/CodeViewer";
import { Loading } from "@/shared/components/Loading";
import { Placeholder } from "@/shared/components/Placeholder";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

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
  const [containerEl, setContainerEl] = useState<HTMLDivElement | null>(null);
  const [editorHeight, setEditorHeight] = useState<number>(450);

  useEffect(() => {
    if (!containerEl) return;

    const updateHeight = () => {
      const rect = containerEl.getBoundingClientRect();
      const mainEl = document.getElementById("main-content");
      const mainPaddingBottom = mainEl
        ? parseFloat(window.getComputedStyle(mainEl).paddingBottom) || 24
        : 24;
      const sectionEl = containerEl.parentElement;
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
  }, [containerEl]);

  if (isPreview ? previewSource.isLoading : source.isLoading) {
    return (
      <Placeholder role="tabpanel" className="flex-1 min-h-105">
        <Loading size="lg" text={t("workflow.loadingCode")} />
      </Placeholder>
    );
  }

  return (
    <section
      role="tabpanel"
      className="flex flex-1 flex-col space-y-5 rounded-surface border border-border bg-surface p-6"
    >
      {isPreview ? (
        previewSource.asset && previewSource.data ? (
          <div ref={setContainerEl} className="w-full min-h-0 flex-1">
            <CodeViewer
              height={`${editorHeight}px`}
              language="python"
              theme={theme === "dark" ? "vs-dark" : "light"}
              value={previewSource.data}
              options={{
                readOnly: true,
                minimap: { enabled: false },
                scrollBeyondLastLine: false,
              }}
            />
          </div>
        ) : previewSource.isError ? (
          <p role="alert">{t("workflow.failed")}</p>
        ) : (
          <OverviewArtifactDropzone
            projectId={modelId}
            isModelPreview
            kind="source_code"
            onUploadSuccess={onUploadSuccess}
          />
        )
      ) : source.isError ? (
        <p role="alert">{t("workflow.failed")}</p>
      ) : source.data ? (
        <div ref={setContainerEl} className="w-full min-h-0 flex-1">
          <CodeViewer
            height={`${editorHeight}px`}
            language="python"
            theme={theme === "dark" ? "vs-dark" : "light"}
            value={source.data}
            options={{
              readOnly: true,
              minimap: { enabled: false },
              scrollBeyondLastLine: false,
            }}
          />
        </div>
      ) : (
        <OverviewArtifactDropzone
          projectId={modelId}
          versionId={effectiveVersionId}
          kind="source_code"
          onUploadSuccess={onUploadSuccess}
        />
      )}
    </section>
  );
}

export default CodeOverviewPage;
