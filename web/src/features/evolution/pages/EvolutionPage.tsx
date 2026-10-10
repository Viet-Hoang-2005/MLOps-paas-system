import { RouteFallback } from "@/app/router/RouteFallback";
import { useEvolution } from "@/features/evolution/hooks/useEvolution";
import {
  EVOLUTION_TABS,
  evolutionParams,
} from "@/features/evolution/evolutionState";
import { VersionLineage } from "@/features/evolution/components/VersionLineage";
import { VersionDetails } from "@/features/evolution/components/VersionDetails";
import { VersionInsights } from "@/features/evolution/components/VersionInsights";
import { VersionMetrics } from "@/features/evolution/components/VersionMetrics";
import { VersionHistory } from "@/features/evolution/components/VersionHistory";
import { VersionDriftSummary } from "@/features/evolution/components/VersionDriftSummary";
import { VersionComparisonDialog } from "@/features/evolution/components/VersionComparisonDialog";
import { runDeploymentPath } from "@/features/deployments/navigation";
import { NoProjectPlaceholder } from "@/features/projects/components/NoProjectPlaceholder";
import { useModelSelection } from "@/features/projects/hooks/useModelSelection";
import { getApiErrorMessage } from "@/shared/api/errors";
import { Badge } from "@/shared/components/Badge";
import { Button } from "@/shared/components/Button";
import { Callout } from "@/shared/components/Callout";
import { PageHeader } from "@/shared/components/PageHeader";
import { GitBranch, GitCompare } from "lucide-react";
import { useState, useRef } from "react";
import { useTranslation } from "react-i18next";
import {
  Navigate,
  useNavigate,
  useParams,
  useSearchParams,
} from "react-router-dom";
import * as Tabs from "@radix-ui/react-tabs";

export default function EvolutionPage() {
  const { modelId } = useParams();
  const { t } = useTranslation("evolution");
  const { selectedModel, loading } = useModelSelection();
  if (modelId) return <EvolutionWorkspace key={modelId} projectId={modelId} />;
  if (loading) return <RouteFallback />;
  if (selectedModel)
    return (
      <Navigate
        to={`/dashboard/projects/${selectedModel.id}/evolution`}
        replace
      />
    );
  return (
    <div className="space-y-6">
      <PageHeader title={t("workspace.title")} />
      <NoProjectPlaceholder
        title={t("workspace.title")}
        description={t("workspace.noProject")}
        icon={<GitBranch className="h-6 w-6" />}
      />
    </div>
  );
}

function EvolutionWorkspace({ projectId }: { projectId: string }) {
  const { t } = useTranslation("evolution");
  const [params, setParams] = useSearchParams();
  const [compare, setCompare] = useState(false);
  const compareButton = useRef<HTMLButtonElement | null>(null);
  const navigate = useNavigate();
  const state = useEvolution(projectId, params.get("versionId"));
  const tab = params.get("tab") ?? "details";
  const version = state.version;
  // A failed background refresh keeps the last loaded data on screen. Only a failure with
  // nothing to show replaces the page; otherwise it is a banner with a retry.
  const loadFailed = Boolean(state.error);
  const blocked = loadFailed && (!state.versions.data || !state.project.data);
  const staleRefresh = loadFailed && !blocked;
  const select = (id: string) => {
    setCompare(false);
    setParams((previous) => evolutionParams(previous, { versionId: id }));
  };
  const changeTab = (value: string) =>
    setParams((previous) =>
      evolutionParams(previous, { tab: value, versionId: state.selected?.id }),
    );
  return (
    <div className="space-y-6">
      <PageHeader title={t("workspace.title")} />
      {state.loading ? (
        <p role="status">{t("workspace.loading")}</p>
      ) : blocked ? (
        <div role="alert" className="space-y-3">
          <p>{getApiErrorMessage(state.error, t("workspace.loadFailed"))}</p>
          <Button variant="secondary" onClick={() => void state.refresh()}>
            {t("workspace.retry")}
          </Button>
        </div>
      ) : (
        <>
          {staleRefresh && (
            <Callout
              variant="danger"
              role="alert"
              description={`${t("workspace.staleData")} ${getApiErrorMessage(state.error, t("workspace.loadFailed"))}`}
              action={
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={() => void state.refresh()}
                >
                  {t("workspace.retry")}
                </Button>
              }
            />
          )}
          {(state.versions.data?.length ?? 0) > 0 && (
            <VersionLineage
              versions={state.versions.data!}
              selectedId={state.selected?.id}
              runningId={state.runningId}
              onSelect={select}
            />
          )}
          {params.has("versionId") && !state.selected ? (
            <p role="alert">{t("workspace.notFound")}</p>
          ) : !state.selected ? (
            <p className="rounded-surface border border-dashed border-border p-10 text-center text-color-muted-foreground">
              {t("workspace.empty")}
            </p>
          ) : state.detail.error && !version ? (
            <div role="alert" className="space-y-3">
              <p>
                {getApiErrorMessage(
                  state.detail.error,
                  t("workspace.loadFailed"),
                )}
              </p>
              <Button
                variant="secondary"
                onClick={() => void state.detail.refetch()}
              >
                {t("workspace.retry")}
              </Button>
            </div>
          ) : !version ? (
            <p role="status">{t("workspace.loading")}</p>
          ) : (
            <section className="overflow-hidden rounded-surface border border-border bg-surface">
              <div className="flex flex-wrap items-start justify-between gap-4 border-b border-border p-6">
                <div className="min-w-0 flex-1 space-y-2">
                  <div className="flex flex-wrap items-center gap-3">
                    <h2 className="break-all text-style-section-title">
                      {state.project.data?.name}{" "}
                      <span className="text-color-muted-foreground">{`v${version.version}`}</span>
                    </h2>
                    {state.runningId === version.id && (
                      <Badge variant="success">{t("workspace.running")}</Badge>
                    )}
                  </div>
                  <p className="text-style-body text-color-muted-foreground">
                    {version.flavor} ·{" "}
                    {t(
                      version.source_job_id
                        ? "workspace.trained"
                        : "workspace.preview",
                    )}
                  </p>
                </div>
                <div className="flex flex-wrap gap-3">
                  <Button
                    variant="secondary"
                    icon={<GitCompare className="h-4 w-4" />}
                    disabled={(state.versions.data?.length ?? 0) < 2}
                    onClick={(event) => {
                      compareButton.current = event.currentTarget;
                      setCompare(true);
                    }}
                  >
                    {t("workspace.compare")}
                  </Button>
                  <Button
                    disabled={
                      !state.deployableBuild || Boolean(state.builds.error)
                    }
                    onClick={() =>
                      state.deployableBuild &&
                      navigate(
                        runDeploymentPath(projectId, state.deployableBuild.id),
                      )
                    }
                  >
                    {t("workspace.openDeployment")}
                  </Button>
                </div>
              </div>
              {state.builds.error && (
                <div role="alert" className="p-4">
                  <p>
                    {getApiErrorMessage(
                      state.builds.error,
                      t("workspace.loadFailed"),
                    )}
                  </p>
                  <Button
                    variant="secondary"
                    onClick={() => void state.builds.refetch()}
                  >
                    {t("workspace.retry")}
                  </Button>
                </div>
              )}
              {!state.builds.isLoading && !state.deployableBuild && (
                <p className="px-6 pt-4 text-style-caption text-color-muted-foreground">
                  {t("workspace.deploymentUnavailable")}
                </p>
              )}
              {!EVOLUTION_TABS.some((value) => value === tab) ? (
                <div role="alert" className="space-y-3 p-6">
                  <p>{t("workspace.invalidTab")}</p>
                  <Button
                    variant="secondary"
                    onClick={() => changeTab("details")}
                  >
                    {t("workspace.backToDetails")}
                  </Button>
                </div>
              ) : (
                <Tabs.Root value={tab} onValueChange={changeTab}>
                  <Tabs.List
                    aria-label={t("workspace.title")}
                    className="flex overflow-x-auto border-b border-border bg-muted px-4 pt-2"
                  >
                    {EVOLUTION_TABS.map((value) => (
                      <Tabs.Trigger
                        key={value}
                        value={value}
                        className="shrink-0 border-b-2 border-transparent px-4 py-3 text-style-body-strong text-color-muted-foreground hover:text-color-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring data-[state=active]:border-primary data-[state=active]:text-color-primary"
                      >
                        {t(`workspace.${value}`)}
                      </Tabs.Trigger>
                    ))}
                  </Tabs.List>
                  <Tabs.Content value="details" className="space-y-6 p-6">
                    <VersionDetails
                      key={version.id}
                      version={version}
                      build={state.build}
                    />
                    <VersionDriftSummary
                      monitors={state.monitors.data ?? []}
                      projectId={projectId}
                      versionId={version.id}
                      loading={state.monitors.isLoading}
                      error={state.monitors.error}
                      retry={() => void state.monitors.refetch()}
                    />
                  </Tabs.Content>
                  <Tabs.Content value="insights" className="p-6">
                    <VersionInsights key={version.id} version={version} />
                  </Tabs.Content>
                  <Tabs.Content value="metrics" className="p-6">
                    <VersionMetrics key={version.id} version={version} />
                  </Tabs.Content>
                  <Tabs.Content value="history" className="p-6">
                    <VersionHistory events={version.events} />
                  </Tabs.Content>
                </Tabs.Root>
              )}
            </section>
          )}
          {compare && version && (
            <VersionComparisonDialog
              key={version.id}
              projectId={projectId}
              versions={state.versions.data ?? []}
              selectedId={version.id}
              onClose={() => setCompare(false)}
              restoreFocus={() => compareButton.current?.focus()}
            />
          )}
        </>
      )}
    </div>
  );
}
