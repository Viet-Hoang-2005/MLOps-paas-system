import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { deployBuild } from "@/features/deployments/api/deployApi";
import {
  deploymentMatchesBuild,
  isDeployableBuild,
  projectDeploymentBlocked,
} from "@/features/deployments/deploymentEligibility";
import {
  useProjectOverview,
  overviewQueryKeys,
} from "@/features/overview/hooks/useProjectOverview";
import {
  useBuild,
  useBuildHistory,
  useDeployment,
  useDeployments,
  deploymentFlowKeys,
} from "./useDeploymentFlow";

export function useRunDeployment(
  projectId: string,
  buildId: string,
  deploymentId: string | null,
) {
  const { t } = useTranslation("projects");
  const client = useQueryClient();
  const build = useBuild(buildId);
  const project = useProjectOverview(projectId);
  const history = useBuildHistory(projectId);
  const attempts = useDeployments();
  const requested = useDeployment(deploymentId);
  const selected = deploymentId
    ? requested.data
    : attempts.data?.find((item) => item.build_id === buildId);
  const mismatch = Boolean(
    (build.data && build.data.project_id !== projectId) ||
    (build.data && selected && !deploymentMatchesBuild(selected, build.data)),
  );
  const error =
    build.error ||
    project.error ||
    history.error ||
    attempts.error ||
    requested.error;
  const loading =
    build.isPending ||
    project.isPending ||
    history.isPending ||
    attempts.isPending ||
    Boolean(deploymentId && requested.isPending);
  const eligible =
    isDeployableBuild(build.data, projectId) &&
    project.data?.deletion_state === "active";
  const busy = projectDeploymentBlocked(
    attempts.data ?? [],
    history.data ?? [],
    selected,
  );
  const running = Boolean(
    build.data?.version_id &&
    project.data?.active_endpoint?.version_id === build.data.version_id &&
    project.data.active_endpoint.deployment_status === "healthy" &&
    project.data.active_endpoint.health_status === "healthy",
  );
  const canDeploy =
    eligible && !loading && !error && !mismatch && !busy && !running;
  const deploy = useMutation({
    mutationFn: () => {
      if (!canDeploy) throw new Error(t("workflow.runNotEligible"));
      return deployBuild(buildId);
    },
    onSuccess: async (result) => {
      client.setQueryData(deploymentFlowKeys.deployment(result.id), result);
      await Promise.all([
        client.invalidateQueries({
          queryKey: deploymentFlowKeys.deployments(),
        }),
        client.invalidateQueries({
          queryKey: deploymentFlowKeys.history(projectId),
        }),
        client.invalidateQueries({
          queryKey: overviewQueryKeys.detail(projectId),
        }),
      ]);
    },
  });
  return {
    build,
    project,
    history,
    selected,
    mismatch,
    error,
    loading,
    eligible,
    busy,
    running,
    canDeploy,
    deploy,
  };
}
