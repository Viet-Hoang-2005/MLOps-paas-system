import { RouteFallback } from "@/app/router/RouteFallback";
import {
  deployBuild,
  getProjectVersions,
} from "@/features/deployments/api/deployApi";
import { useBuildHistory } from "@/features/deployments/hooks/useDeploymentFlow";
import { SnapshotComparison } from "@/features/evolution/components/SnapshotComparison";
import { SnapshotMetadata } from "@/features/evolution/components/SnapshotMetadata";
import { evolutionQueryKeys } from "@/features/evolution/queryKeys";
import { useProjectOverview } from "@/features/overview/hooks/useProjectOverview";
import { NoProjectPlaceholder } from "@/features/projects/components/NoProjectPlaceholder";
import { useModelSelection } from "@/features/projects/hooks/useModelSelection";
import { getApiErrorMessage } from "@/shared/api/errors";
import { Badge } from "@/shared/components/Badge";
import { Button } from "@/shared/components/Button";
import { ConfirmDialog } from "@/shared/components/ConfirmDialog";
import { PageHeader } from "@/shared/components/PageHeader";
import { Select } from "@/shared/components/Select";
import { formatDateTime } from "@/shared/i18n/formatters";
import { useMutation, useQuery } from "@tanstack/react-query";
import { GitBranch } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import {
  Navigate,
  useNavigate,
  useParams,
  useSearchParams,
} from "react-router-dom";

export default function EvolutionPage() {
  const { modelId } = useParams();
  const { t, i18n } = useTranslation("projects");
  const { t: tCommon } = useTranslation("common");
  const { selectedModel, loading: isModelLoading } = useModelSelection();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const [confirm, setConfirm] = useState(false);
  const versions = useQuery({
    queryKey: evolutionQueryKeys.versions(modelId ?? ""),
    queryFn: () => getProjectVersions(modelId!),
    enabled: Boolean(modelId),
  });
  const builds = useBuildHistory(modelId);
  const project = useProjectOverview(modelId);
  const version = params.has("versionId")
    ? versions.data?.find((item) => item.id === params.get("versionId"))
    : versions.data?.[0];
  const build = builds.data?.find(
    (item) => item.version_id === version?.id && item.status === "ready",
  );
  const deploy = useMutation({
    mutationFn: () => deployBuild(build!.id),
    onSuccess: (deployment) =>
      navigate(
        `/dashboard/deployments/new?projectId=${modelId}&buildId=${build!.id}&step=deploy&deploymentId=${deployment.id}`,
      ),
  });
  if (!modelId) {
    if (isModelLoading) return <RouteFallback />;
    if (selectedModel) {
      return (
        <Navigate
          to={`/dashboard/projects/${selectedModel.id}/evolution`}
          replace
        />
      );
    }
    return (
      <div className="flex w-full flex-1 flex-col space-y-6">
        <PageHeader title={t("workflow.evolution")} />
        <NoProjectPlaceholder
          title={tCommon("navigation.modelEvolution")}
          description={t("workflow.noProjectEvolution")}
          icon={<GitBranch className="h-6 w-6" />}
        />
      </div>
    );
  }
  return (
    <div className="space-y-6">
      <PageHeader title={t("workflow.evolution")} />
      <Select
        value={version?.id || ""}
        onChange={(id) => setParams({ versionId: id })}
        options={(versions.data ?? []).map((item) => ({
          value: item.id,
          label: `v${item.version} · ${formatDateTime(item.registered_at, i18n.language)}`,
        }))}
        placeholder={t("workflow.selectVersion")}
      />
      {version ? (
        <section className="space-y-5 rounded-surface border border-border bg-surface p-6">
          <div className="flex gap-3">
            <h2 className="text-style-heading">{`v${version.version}`}</h2>
            {project.data?.active_endpoint?.version_id === version.id && (
              <Badge variant="success">{t("workflow.running")}</Badge>
            )}
          </div>
          <p>
            {version.flavor} ·{" "}
            {version.source_job_id
              ? t("workflow.trained")
              : t("workflow.preview")}
          </p>
          {version.source_job_id && (
            <Button
              variant="secondary"
              onClick={() =>
                navigate(
                  `/dashboard/training/jobs/${version.source_job_id}/overview`,
                )
              }
            >
              {t("workflow.trainingLineage")}: {version.source_job_id}
            </Button>
          )}
          <ol
            aria-label={t("workflow.evolution")}
            className="flex flex-wrap gap-2"
          >
            {[...(versions.data ?? [])].reverse().map((item) => (
              <li key={item.id}>
                <Button
                  variant={item.id === version.id ? "primary" : "secondary"}
                  onClick={() => setParams({ versionId: item.id })}
                >{`v${item.version}`}</Button>
              </li>
            ))}
          </ol>
          <ul className="text-style-code-sm">
            {version.artifacts.map((artifact) => (
              <li key={artifact.id}>
                {artifact.kind}: {artifact.name}
              </li>
            ))}
          </ul>
          <SnapshotMetadata version={version} />
          <SnapshotComparison
            versions={versions.data ?? []}
            selected={version}
          />
          <pre className="overflow-auto text-style-code-sm">
            {version.requirements_snapshot}
          </pre>
          <Button
            disabled={!build || deploy.isPending}
            onClick={() => setConfirm(true)}
          >
            {t("workflow.deploy")}
          </Button>
        </section>
      ) : (
        <p>{t("workflow.noVersions")}</p>
      )}
      {(versions.error || deploy.error) && (
        <p role="alert">
          {getApiErrorMessage(
            versions.error || deploy.error,
            t("workflow.failed"),
          )}
        </p>
      )}
      <ConfirmDialog
        open={confirm}
        title={t("workflow.deploy")}
        description={t("workflow.deployHint")}
        loading={deploy.isPending}
        onConfirm={() => deploy.mutate()}
        onCancel={() => setConfirm(false)}
      />
    </div>
  );
}
