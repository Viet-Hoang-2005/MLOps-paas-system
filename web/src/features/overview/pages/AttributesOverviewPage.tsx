import { ModelAttributesView } from "@/features/overview/components/ModelAttributesView";
import type { ModelAttributesResponse } from "@/shared/api/catalogApi";
import { Loading } from "@/shared/components/Loading";
import { Placeholder } from "@/shared/components/Placeholder";
import { useTranslation } from "react-i18next";

export interface AttributesOverviewPageProps {
  modelId: string;
  attributes?: ModelAttributesResponse | null;
  isLoading: boolean;
}

export function AttributesOverviewPage({
  modelId,
  attributes,
  isLoading,
}: AttributesOverviewPageProps) {
  const { t } = useTranslation("overview");

  if (isLoading) {
    return (
      <Placeholder role="tabpanel" className="flex-1 min-h-105">
        <Loading size="lg" text={t("workflow.loadingAttributes")} />
      </Placeholder>
    );
  }

  return (
    <ModelAttributesView
      attributes={attributes}
      projectId={modelId}
    />
  );
}

export default AttributesOverviewPage;

