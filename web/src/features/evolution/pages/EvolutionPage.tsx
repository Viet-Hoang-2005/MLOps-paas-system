import { RouteFallback } from "@/app/router/RouteFallback";
import { useEvolution } from "@/features/evolution/hooks/useEvolution";
import {
  evolutionParams,
  normalizeEvolutionTab,
} from "@/features/evolution/evolutionState";
import { VersionLineage } from "@/features/evolution/components/VersionLineage";
import { InformationEvolutionPage } from "@/features/evolution/pages/InformationEvolutionPage";
import { MonitoringEvolutionPage } from "@/features/evolution/pages/MonitoringEvolutionPage";
import { AttributesEvolutionPage } from "@/features/evolution/pages/AttributesEvolutionPage";
import { CodeEvolutionPage } from "@/features/evolution/pages/CodeEvolutionPage";
import { DataEvolutionPage } from "@/features/evolution/pages/DataEvolutionPage";
import { ComparisonVersionDialog } from "@/features/evolution/components/ComparisonVersionDialog";
import { runDeploymentPath } from "@/features/deployments/navigation";
import { NoProjectPlaceholder } from "@/features/projects/components/NoProjectPlaceholder";
import { useModelSelection } from "@/features/projects/hooks/useModelSelection";
import { getApiErrorMessage } from "@/shared/api/errors";
import { Button } from "@/shared/components/Button";
import { Callout } from "@/shared/components/Callout";
import { PageHeader } from "@/shared/components/PageHeader";
import { PageTabs } from "@/shared/components/PageTabs";
import {
  Activity,
  Code,
  FileSpreadsheet,
  GitBranch,
  GitCompare,
  Info,
  SlidersHorizontal,
  Play,
} from "lucide-react";
import { useState, useRef } from "react";
import { useTranslation } from "react-i18next";
import {
  Navigate,
  useNavigate,
  useParams,
  useSearchParams,
} from "react-router-dom";

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
  const tab = normalizeEvolutionTab(params.get("tab"));
  const version = state.version;

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
    <div className="flex flex-col lg:flex-row items-stretch gap-6 min-h-0 flex-1 lg:h-[calc(100vh-7rem)] lg:max-h-[calc(100vh-7rem)]">
      {/* Main Content Area */}
      <div className="flex-1 min-w-0 flex flex-col h-full min-h-0 gap-6 w-full">
        <div className="shrink-0">
          <PageHeader title={t("workspace.title")} />
        </div>
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
              <div className="shrink-0">
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
              </div>
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
              <>
                {/* Heading section */}
                <section className="shrink-0 space-y-4 rounded-surface border border-border bg-surface p-6">
                  <div className="flex flex-wrap items-start justify-between gap-4">
                    <div className="space-y-2 min-w-0 flex-1">
                      <h1 className="text-style-page-title text-color-foreground">
                        {state.project.data?.name}
                      </h1>
                      <p className="text-color-muted-foreground">
                        {state.project.data?.description ||
                          t("workspace.noDescription")}
                      </p>
                    </div>
                    <div className="flex flex-wrap items-center gap-3">
                      <Button
                        size="md"
                        variant="primary"
                        icon={<Play className="h-4 w-4"/>}
                        disabled={
                          !state.deployableBuild || Boolean(state.builds.error)
                        }
                        onClick={() =>
                          state.deployableBuild &&
                          navigate(
                            runDeploymentPath(
                              projectId,
                              state.deployableBuild.id,
                            ),
                          )
                        }
                      >
                        {t("workspace.openDeployment")}
                      </Button>
                      <Button
                        size="icon"
                        variant="secondary"
                        icon={<GitCompare className="h-4 w-4" />}
                        aria-label={t("workspace.compare")}
                        title={t("workspace.compare")}
                        disabled={(state.versions.data?.length ?? 0) < 2}
                        onClick={(event) => {
                          compareButton.current = event.currentTarget;
                          setCompare(true);
                        }}
                      />
                    </div>
                  </div>

                  {state.builds.error && (
                    <div role="alert" className="pt-2">
                      <p className="text-color-danger text-style-caption">
                        {getApiErrorMessage(
                          state.builds.error,
                          t("workspace.loadFailed"),
                        )}
                      </p>
                    </div>
                  )}
                  {!state.builds.isLoading && !state.deployableBuild && (
                    <p className="text-style-caption text-color-muted-foreground">
                      {t("workspace.deploymentUnavailable")}
                    </p>
                  )}
                </section>

                {/* Body Card wrapping PageTabs and Tab Contents */}
                <section className="flex-1 min-h-0 rounded-surface border border-border bg-surface flex flex-col overflow-hidden shadow-xs">
                  {/* Page Tabs Header */}
                  <div className="border-b border-border px-6 pt-2 shrink-0 bg-surface">
                    <PageTabs
                      tabs={[
                        {
                          label: t("workspace.information"),
                          icon: Info,
                          isActive: tab === "information",
                          onClick: () => changeTab("information"),
                        },
                        {
                          label: t("workspace.monitoring"),
                          icon: Activity,
                          isActive: tab === "monitoring",
                          onClick: () => changeTab("monitoring"),
                        },
                        {
                          label: t("workspace.attributes"),
                          icon: SlidersHorizontal,
                          isActive: tab === "attributes",
                          onClick: () => changeTab("attributes"),
                        },
                        {
                          label: t("workspace.code"),
                          icon: Code,
                          isActive: tab === "code",
                          onClick: () => changeTab("code"),
                        },
                        {
                          label: t("workspace.data"),
                          icon: FileSpreadsheet,
                          isActive: tab === "data",
                          onClick: () => changeTab("data"),
                        },
                      ]}
                    />
                  </div>

                  {/* Tab Contents with separate scrollbar */}
                  <div
                    key={tab}
                    className="flex-1 min-h-0 overflow-y-auto p-6 custom-scrollbar overscroll-contain flex flex-col"
                    onWheel={(e) => e.stopPropagation()}
                  >
                    {tab === "information" && (
                      <InformationEvolutionPage
                        version={version}
                        build={state.build}
                        runningId={state.runningId}
                      />
                    )}
                    {tab === "monitoring" && (
                      <MonitoringEvolutionPage
                        projectId={projectId}
                        versionId={version.id}
                      />
                    )}
                    {tab === "attributes" && (
                      <AttributesEvolutionPage
                        projectId={projectId}
                        version={version}
                      />
                    )}
                    {tab === "code" && (
                      <CodeEvolutionPage
                        projectId={projectId}
                        version={version}
                      />
                    )}
                    {tab === "data" && (
                      <DataEvolutionPage
                        projectId={projectId}
                        version={version}
                      />
                    )}
                  </div>
                </section>
              </>
            )}
          </>
        )}
      </div>

      {/* Outermost right: Vertical Version Lineage */}
      {!state.loading && !blocked && (state.versions.data?.length ?? 0) > 0 && (
        <aside
          className="custom-scrollbar w-full lg:w-20 shrink-0 sticky top-0 lg:h-full lg:max-h-[calc(100vh-7rem)] rounded-surface border border-border bg-surface py-5 px-2 flex flex-col items-center overflow-x-auto lg:overflow-y-auto overscroll-contain shadow-xs"
          onWheel={(e) => e.stopPropagation()}
        >
          <VersionLineage
            versions={state.versions.data!}
            selectedId={state.selected?.id}
            runningId={state.runningId}
            projectStatus={state.project.data?.lifecycle_status}
            onSelect={select}
            orientation="vertical"
          />
        </aside>
      )}

      {compare && version && (
        <ComparisonVersionDialog
          key={version.id}
          projectId={projectId}
          versions={state.versions.data ?? []}
          selectedId={version.id}
          onClose={() => setCompare(false)}
          restoreFocus={() => compareButton.current?.focus()}
        />
      )}
    </div>
  );
}
