import { OverviewArtifactDropzone } from "@/features/overview/components/OverviewArtifactDropzone";
import type { PreviewAsset } from "@/features/projects/api/previewApi";
import { DataViewer } from "@/shared/components/DataViewer";
import { Loading } from "@/shared/components/Loading";
import { Placeholder } from "@/shared/components/Placeholder";
import { useTranslation } from "react-i18next";

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

  if (isPreview ? previewReference.isLoading : reference.isLoading) {
    return (
      <Placeholder role="tabpanel" className="flex-1 min-h-105">
        <Loading size="lg" text={t("workflow.loadingData")} />
      </Placeholder>
    );
  }

  return (
    <section
      role="tabpanel"
      className="flex flex-1 flex-col space-y-5 rounded-surface border border-border bg-surface p-6"
    >
      {isPreview ? (
        previewReference.asset && previewReference.data ? (
          <DataViewer
            title={previewReference.asset.name}
            initialCsvText={previewReference.data}
            readOnly
          />
        ) : previewReference.isError ? (
          <p role="alert">{t("workflow.failed")}</p>
        ) : (
          <OverviewArtifactDropzone
            projectId={modelId}
            isModelPreview
            kind="reference_data"
            onUploadSuccess={onUploadSuccess}
          />
        )
      ) : reference.isError ? (
        <p role="alert">{t("workflow.failed")}</p>
      ) : reference.data ? (
        <DataViewer
          title={referenceDataName}
          initialCsvText={reference.data}
          readOnly
        />
      ) : (
        <OverviewArtifactDropzone
          projectId={modelId}
          versionId={effectiveVersionId}
          kind="reference_data"
          onUploadSuccess={onUploadSuccess}
        />
      )}
    </section>
  );
}

export default DataOverviewPage;

