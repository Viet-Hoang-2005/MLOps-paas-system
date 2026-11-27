import { RouteFallback } from "@/app/router/RouteFallback";
import { deleteModelVersion } from "@/features/evolution/api/evolutionApi";
import { evolutionQueryKeys } from "@/features/evolution/queryKeys";
import { useEvolution } from "@/features/evolution/hooks/useEvolution";
import {
  evolutionParams,
  normalizeEvolutionTab,
} from "@/features/evolution/evolutionState";
import { catalogQueryKeys } from "@/features/projects/queryKeys";
import type { ModelVersion } from "@/features/projects/types";
import { deploymentFlowKeys } from "@/features/deployments/queryKeys";
import { driftQueryKeys } from "@/features/monitoring/queryKeys";
import { VersionLineage } from "@/features/evolution/components/VersionLineage";
import { InformationEvolutionPage } from "@/features/evolution/pages/InformationEvolutionPage";
import { MonitoringEvolutionPage } from "@/features/evolution/pages/MonitoringEvolutionPage";
import { AttributesEvolutionPage } from "@/features/evolution/pages/AttributesEvolutionPage";
import { CodeEvolutionPage } from "@/features/evolution/pages/CodeEvolutionPage";
import { DataEvolutionPage } from "@/features/evolution/pages/DataEvolutionPage";
import { ComparisonVersionDialog } from "@/features/evolution/components/ComparisonVersionDialog";
import {
  buildDeploymentPath,
  runDeploymentPath,
} from "@/features/deployments/navigation";
import { routes } from "@/app/router/paths";
import { Placeholder } from "@/shared/components/Placeholder";
import { useModelSelection } from "@/features/projects/hooks/useModelSelection";
import { getApiErrorMessage } from "@/shared/api/errors";
import { Button } from "@/shared/components/Button";
import { Callout } from "@/shared/components/Callout";
import { ConfirmDialog } from "@/shared/components/ConfirmDialog";
import { PageHeader } from "@/shared/components/PageHeader";
import { PageTabs } from "@/shared/components/PageTabs";
import { toast } from "@/shared/lib/toastStore";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Activity,
  Code,
  FileSpreadsheet,
  GitBranch,
  GitCompare,
  Info,
  SlidersHorizontal,
  Play,
  Plus,
  Trash2,
} from "lucide-react";
import { useEffect, useState, useRef } from "react";
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
  const { t: tCommon } = useTranslation("common");
  const { t: tProjects } = useTranslation("projects");
  const { selectedModel, loading } = useModelSelection();
  const navigate = useNavigate();

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
    <div className="flex w-full flex-1 flex-col space-y-6">
      <PageHeader
        title={t("workspace.title")}
        actions={<ProjectPageSelect />}
      />
      <Placeholder
        title={t("workspace.title")}
        description={t("workspace.noProject")}
        icon={<GitBranch className="h-6 w-6" />}
        additional={tCommon("modelSelector.empty")}
        action={
          <Button
            size="md"
            icon={<Plus className="h-4 w-4" />}
            onClick={() => navigate(routes.newProject)}
          >
            {tProjects("workflow.newProject")}
          </Button>
        }
      />
    </div>
  );
}

function EvolutionWorkspace({ projectId }: { projectId: string }) {
  const { t } = useTranslation("evolution");
  const { t: tCommon } = useTranslation("common");
  const [params, setParams] = useSearchParams();
  const [compare, setCompare] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const compareButton = useRef<HTMLButtonElement | null>(null);
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const state = useEvolution(projectId, params.get("versionId"));
  const tab = normalizeEvolutionTab(params.get("tab"));
  const version = state.version;
  const pendingDeletions = useRef(new Set<string>());
  const versions = state.versions.data;
  const versionsKey = evolutionQueryKeys.versions(projectId);

  useEffect(() => {
    if (!versions) return;
    for (const item of versions) {
      if (item.deletion_requested) pendingDeletions.current.add(item.id);
    }
    const completed = [...pendingDeletions.current].filter(
      (id) => !versions.some((item) => item.id === id),
    );
    if (completed.length === 0) return;
    for (const id of completed) {
      pendingDeletions.current.delete(id);
      queryClient.removeQueries({ queryKey: evolutionQueryKeys.snapshot(id) });
    }
    if (completed.includes(params.get("versionId") ?? "")) {
      setParams(
        (previous) => {
          const next = new URLSearchParams(previous);
          next.delete("versionId");
          return next;
        },
        { replace: true },
      );
    }
    void Promise.all([
      queryClient.invalidateQueries({
        queryKey: catalogQueryKeys.project(projectId),
      }),
      queryClient.invalidateQueries({ queryKey: catalogQueryKeys.projects() }),
      queryClient.invalidateQueries({
        queryKey: deploymentFlowKeys.history(projectId),
      }),
      queryClient.invalidateQueries({
        queryKey: deploymentFlowKeys.deployments(),
      }),
      queryClient.invalidateQueries({
        queryKey: driftQueryKeys.monitors(projectId),
      }),
    ]);
  }, [params, projectId, queryClient, setParams, versions]);

  const deleteMutation = useMutation({
    mutationFn: (target: ModelVersion) => deleteModelVersion(target.id),
    onSuccess: async (_data, target) => {
      setConfirmDelete(false);
      pendingDeletions.current.add(target.id);
      await queryClient.cancelQueries({ queryKey: versionsKey });
      queryClient.setQueryData<ModelVersion[]>(versionsKey, (items) =>
        items?.map((item) =>
          item.id === target.id ? { ...item, deletion_requested: true } : item,
        ),
      );
      toast.success(
        t("workspace.deleteVersionQueued", { version: target.version }),
      );
      await queryClient.invalidateQueries({
        queryKey: versionsKey,
      });
    },
    onError: (err) => {
      setConfirmDelete(false);
      toast.error(getApiErrorMessage(err, t("workspace.deleteVersionFailed")));
    },
  });

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

  if (state.loading) {
    return (
      <div className="flex w-full flex-1 flex-col space-y-6">
        <PageHeader
          title={t("workspace.title")}
          actions={<ProjectPageSelect />}
        />
        <p role="status">{t("workspace.loading")}</p>
      </div>
    );
  }

  if (blocked) {
    return (
      <div className="flex w-full flex-1 flex-col space-y-6">
        <PageHeader
          title={t("workspace.title")}
          actions={<ProjectPageSelect />}
        />
        <div role="alert" className="space-y-3">
          <p>{getApiErrorMessage(state.error, t("workspace.loadFailed"))}</p>
          <Button variant="secondary" onClick={() => void state.refresh()}>
            {t("workspace.retry")}
          </Button>
        </div>
      </div>
    );
  }

  if ((state.versions.data?.length ?? 0) === 0) {
    return (
      <div className="flex w-full flex-1 flex-col space-y-6">
        <PageHeader
          title={t("workspace.title")}
          actions={<ProjectPageSelect />}
        />
        <Placeholder
          title={t("workspace.title")}
          description={t("workspace.empty")}
          icon={<GitBranch className="h-6 w-6" />}
          action={
            <Button
              size="md"
              icon={<Plus className="h-4 w-4" />}
              onClick={() => navigate(buildDeploymentPath({ projectId }))}
            >
              {t("workspace.buildAndRegister")}
            </Button>
          }
        />
      </div>
    );
  }

  return (
    <div className="flex flex-col w-full flex-1 min-h-0 h-[calc(100vh-7.5rem)] max-h-[calc(100vh-7.5rem)] space-y-6 overflow-hidden">
      <div className="shrink-0">
        <PageHeader
          title={t("workspace.title")}
          actions={<ProjectPageSelect />}
        />
      </div>

      <div className="flex flex-col lg:flex-row items-stretch gap-6 flex-1 min-h-0 overflow-hidden">
        {/* Main Content Area */}
        <div className="flex-1 min-w-0 flex flex-col min-h-0 gap-6 w-full">
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

          {!state.selected ? (
            <p role="alert">{t("workspace.notFound")}</p>
          ) : state.selected.deletion_requested ? (
            <p role="status">
              {t("workspace.deletingVersion", {
                version: state.selected.version,
              })}
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
              <section className="shrink-0 space-y-4 rounded-surface border border-border bg-surface p-6 shadow-xs">
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
                      icon={<Play className="h-4 w-4" />}
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
                    <Button
                      size="icon"
                      variant="danger"
                      icon={<Trash2 className="h-4 w-4" />}
                      aria-label={t("workspace.deleteVersion")}
                      title={t("workspace.deleteVersion")}
                      disabled={deleteMutation.isPending}
                      onClick={() => setConfirmDelete(true)}
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

              {/* Body Card wrapping PageTabs and Tab Contents with its own scrollbar */}
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
        </div>

        {/* Outermost right: Vertical Version Lineage */}
        {!state.loading &&
          !blocked &&
          (state.versions.data?.length ?? 0) > 0 && (
            <aside className="custom-scrollbar w-full lg:w-20 shrink-0 self-stretch rounded-surface border border-border bg-surface py-5 px-2 flex flex-col items-center overflow-x-auto lg:overflow-y-auto overscroll-contain shadow-xs">
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
      </div>

      {compare && version && !state.selected?.deletion_requested && (
        <ComparisonVersionDialog
          key={version.id}
          projectId={projectId}
          versions={state.versions.data ?? []}
          selectedId={version.id}
          onClose={() => setCompare(false)}
          restoreFocus={() => compareButton.current?.focus()}
        />
      )}

      {version && !state.selected?.deletion_requested && (
        <ConfirmDialog
          open={confirmDelete}
          tone="danger"
          title={t("workspace.deleteVersionTitle", {
            version: version.version,
          })}
          description={
            <div className="space-y-3">
              <p>{t("workspace.deleteVersionDescription")}</p>
              {version.id === state.runningId && (
                <p className="font-medium text-color-danger">
                  {t("workspace.deleteVersionRunningWarning")}
                </p>
              )}
            </div>
          }
          confirmText={t("workspace.deleteVersion")}
          cancelText={tCommon("actions.cancel")}
          loading={deleteMutation.isPending}
          onConfirm={() => deleteMutation.mutate(version)}
          onCancel={() => {
            if (!deleteMutation.isPending) setConfirmDelete(false);
          }}
        />
      )}
    </div>
  );
}
import { ProjectPageSelect } from "@/features/projects/components/ProjectPageSelect";
