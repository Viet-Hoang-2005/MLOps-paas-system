import { ModelAttributesView } from "@/features/overview/components/ModelAttributesView";
import type { ModelAttributesResponse } from "@/shared/api/catalogApi";
import { Button } from "@/shared/components/Button";
import { Loading } from "@/shared/components/Loading";
import { Placeholder } from "@/shared/components/Placeholder";
import { useTranslation } from "react-i18next";

export interface AttributesOverviewPageProps {
  modelId: string;
  effectiveVersionId?: string;
  isPreview?: boolean;
  attributes?: ModelAttributesResponse | null;
  isLoading: boolean;
  isError?: boolean;
  onRetry?: () => void;
}

export function AttributesOverviewPage({
  modelId,
  effectiveVersionId,
  isPreview,
  attributes,
  isLoading,
  isError,
  onRetry,
}: AttributesOverviewPageProps) {
  const { t } = useTranslation("overview");

  if (isLoading && !attributes) {
    return (
      <Placeholder role="tabpanel" className="flex-1 min-h-105">
        <Loading size="lg" text={t("workflow.loadingAttributes")} />
      </Placeholder>
    );
  }

  if (isError && !attributes) {
    return (
      <Placeholder role="tabpanel" className="flex-1 min-h-105">
        <div className="flex flex-col items-center gap-4 text-center">
          <p className="text-style-body text-color-danger">
            {t("workflow.loadAttributesFailed", "Failed to load model attributes.")}
          </p>
          {onRetry && (
            <Button variant="secondary" size="sm" onClick={onRetry}>
              {t("workflow.retry", "Retry")}
            </Button>
          )}
        </div>
      </Placeholder>
    );
  }

  return (
    <ModelAttributesView
      attributes={attributes}
      projectId={modelId}
      versionId={effectiveVersionId}
      isPreview={isPreview}
    />
  );
}

export default AttributesOverviewPage;

