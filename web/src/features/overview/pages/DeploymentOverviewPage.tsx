import { buildDeploymentPath } from "@/features/deployments/navigation";
import { ModelPredictionsTesting } from "@/features/overview/components/ModelPredictionsTesting";
import { ModelStatusLine } from "@/features/overview/components/ModelStatusLine";
import { ResourceUsageChart } from "@/features/overview/components/ResourceUsageChart";
import type { ModelProject } from "@/features/projects/types";
import { Button } from "@/shared/components/Button";
import { Placeholder } from "@/shared/components/Placeholder";
import { Box } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

export interface DeploymentOverviewPageProps {
  model: ModelProject;
  modelId: string;
  hasRunning: boolean;
  healthUnavailable?: boolean;
}

export function DeploymentOverviewPage({
  model,
  modelId,
  hasRunning,
  healthUnavailable = false,
}: DeploymentOverviewPageProps) {
  const { t } = useTranslation("overview");
  const { t: tCommon } = useTranslation("common");
  const navigate = useNavigate();

  if (!hasRunning) {
    return (
      <Placeholder
        title={tCommon("navigation.deployment")}
        description={`${t("workflow.noRunning")} ${t("workflow.healthNotChecked")}`}
        icon={<Box className="h-6 w-6" />}
        action={
          <Button size="md" onClick={() => navigate(buildDeploymentPath())}>
            {t("workflow.deploy")}
          </Button>
        }
      />
    );
  }

  return (
    <div role="tabpanel" className="space-y-6">
      <ModelStatusLine model={model} healthUnavailable={healthUnavailable} />
      <ResourceUsageChart
        projectId={modelId}
        deploymentId={model.active_endpoint?.deployment_id ?? ""}
      />
      <ModelPredictionsTesting model={model} />
    </div>
  );
}

export default DeploymentOverviewPage;

