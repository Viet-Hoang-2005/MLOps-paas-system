import { RouteFallback } from "@/app/router/RouteFallback";
import { useTheme } from "@/app/theme/useTheme";
import { RuntimeMetrics } from "@/features/overview/components/RuntimeMetrics";
import {
  useProjectOverview,
  useRunningSource,
  useSnapshotText,
} from "@/features/overview/hooks/useProjectOverview";
import { EditMetadataDialog } from "@/features/projects/components/EditMetadataDialog";
import { NoProjectPlaceholder } from "@/features/projects/components/NoProjectPlaceholder";
import { useModelSelection } from "@/features/projects/hooks/useModelSelection";
import { catalogQueryKeys } from "@/features/projects/queryKeys";
import {
  deleteModelProject,
  updateModelProject,
} from "@/shared/api/catalogApi";
import { getApiErrorMessage } from "@/shared/api/errors";
import { Badge } from "@/shared/components/Badge";
import { Button } from "@/shared/components/Button";
import { ConfirmDialog } from "@/shared/components/ConfirmDialog";
import { DataViewer } from "@/shared/components/DataViewer";
import { LazyCodeEditor } from "@/shared/components/LazyCodeEditor";
import { PageHeader } from "@/shared/components/PageHeader";
import { PageTabs } from "@/shared/components/PageTabs";
import { Placeholder } from "@/shared/components/Placeholder";
import { Select } from "@/shared/components/Select";
import { formatDateTime } from "@/shared/i18n/formatters";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Box,
  Code,
  Database,
  Home,
  Info,
  PenLine,
  Settings2,
  Trash2,
} from "lucide-react";
import { lazy, Suspense, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  Navigate,
  useNavigate,
  useParams,
  useSearchParams,
} from "react-router-dom";

const ModelTestingPage = lazy(
  () => import("@/features/overview/pages/ModelTestingPage"),
);

export default function ProjectOverviewPage() {
  const { modelId } = useParams();
  const { t, i18n } = useTranslation("overview");
  const { t: tCommon } = useTranslation("common");
  const { selectedModel, loading: isModelLoading } = useModelSelection();
  const { resolvedTheme } = useTheme();
  const navigate = useNavigate();
  const client = useQueryClient();
  const [params, setParams] = useSearchParams();
  const tab = params.get("tab") || "deployment";
  const project = useProjectOverview(modelId);
  const model = project.data;
  const source = useRunningSource(
    tab === "code" ? modelId : undefined,
    model?.active_endpoint?.version_id,
  );
  const reference = useSnapshotText(
    tab === "data" ? model?.reference_data?.download_url : undefined,
    model?.active_endpoint?.version_id,
  );
  const [editMetadataOpen, setEditMetadataOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const update = useMutation({
    mutationFn: async (payload: {
      name: string;
      description: string;
      access_mode: "private" | "public";
    }) => updateModelProject(modelId!, payload),
    onSuccess: async () => {
      setEditMetadataOpen(false);
      await project.refetch();
      await client.invalidateQueries({ queryKey: catalogQueryKeys.projects() });
    },
  });
  const remove = useMutation({
    mutationFn: () => deleteModelProject(modelId!),
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey: catalogQueryKeys.projects() });
      navigate("/dashboard/projects");
    },
  });
  if (!modelId) {
    if (isModelLoading) return <RouteFallback />;
    if (selectedModel) {
      return (
        <Navigate
          to={`/dashboard/projects/${selectedModel.id}/overview`}
          replace
        />
      );
    }
    return (
      <div className="flex w-full flex-1 flex-col space-y-6">
        <PageHeader title={tCommon("navigation.home")} />
        <NoProjectPlaceholder
          title={tCommon("navigation.home")}
          description={t("workflow.noProjectOverview")}
          icon={<Home className="h-6 w-6" />}
        />
      </div>
    );
  }
  if (project.isError)
    return (
      <p role="alert">
        {getApiErrorMessage(project.error, t("workflow.failed"))}
      </p>
    );
  if (!model) return <p>{t("workflow.loading")}</p>;
  const hasRunning = Boolean(model.active_endpoint);
  return (
    <div className="flex w-full flex-1 flex-col space-y-6">
      <PageHeader title={tCommon("navigation.home")} />
      <section className="space-y-4 rounded-surface border border-border bg-surface p-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="space-y-2">
            <div className="flex flex-wrap items-center gap-3">
              <h1 className="text-style-page-title text-color-foreground">
                {model.name}
              </h1>
              <Badge
                variant={
                  model.lifecycle_status === "running" ? "success" : "neutral"
                }
              >
                {t(`workflow.${model.lifecycle_status}`)}
                {model.preview_changed
                  ? ` · ${t("workflow.previewChanged")}`
                  : ""}
              </Badge>
            </div>
            <p className="text-color-muted-foreground">
              {model.description || t("noDescription")}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Button
              size="icon"
              variant="secondary"
              icon={<PenLine className="h-4 w-4" />}
              onClick={() => setEditMetadataOpen(true)}
              aria-label={t("workflow.editMetadata")}
              title={t("workflow.editMetadata")}
            />
            <Button
              size="icon"
              variant="secondary"
              icon={<Settings2 className="h-4 w-4" />}
              onClick={() => navigate(`/dashboard/projects/${modelId}/edit`)}
              aria-label={t("workflow.editPreview")}
              title={t("workflow.editPreview")}
            />
            <Button
              size="icon"
              variant="danger"
              icon={<Trash2 className="h-4 w-4" />}
              onClick={() => setDeleting(true)}
              aria-label={t("workflow.delete")}
              title={t("workflow.delete")}
            />
          </div>
        </div>
        {model.deletion_state === "delete_failed" && (
          <p role="alert" className="text-color-danger">
            {t("workflow.deletionFailed")} {model.deletion_error}
          </p>
        )}
      </section>
      <div className="border-b border-border">
        <PageTabs
          tabs={[
            {
              label: t("workflow.deployment"),
              icon: Box,
              isActive: tab === "deployment",
              onClick: () => setParams({ tab: "deployment" }),
            },
            {
              label: t("workflow.code"),
              icon: Code,
              isActive: tab === "code",
              onClick: () => setParams({ tab: "code" }),
            },
            {
              label: t("workflow.data"),
              icon: Database,
              isActive: tab === "data",
              onClick: () => setParams({ tab: "data" }),
            },
            {
              label: t("workflow.information"),
              icon: Info,
              isActive: tab === "information",
              onClick: () => setParams({ tab: "information" }),
            },
          ]}
        />
      </div>
      {tab !== "information" && !hasRunning ? (
        <Placeholder
          title={tCommon("navigation.deployment")}
          description={t("workflow.noRunning")}
          icon={<Box className="h-6 w-6" />}
          showModelName={false}
          action={
            <Button
              size="md"
              onClick={() =>
                navigate(`/dashboard/deployments/new?projectId=${modelId}`)
              }
            >
              {t("workflow.deploy")}
            </Button>
          }
        />
      ) : (
        <section
          role="tabpanel"
          className="space-y-5 rounded-surface border border-border bg-surface p-6"
        >
          {tab === "information" ? (
            <>
              <p>{model.name}</p>
              <p>{model.description}</p>
              <p>{model.flavor}</p>
              <p>
                {formatDateTime(model.created_at, i18n.language)} ·{" "}
                {formatDateTime(model.updated_at, i18n.language)}
              </p>
              <Select
                value={model.access_mode}
                onChange={(value) =>
                  update.mutate({
                    name: model.name,
                    description: model.description,
                    access_mode: value as "private" | "public",
                  })
                }
                options={[
                  { value: "private", label: t("workflow.private") },
                  { value: "public", label: t("workflow.public") },
                ]}
              />
            </>
          ) : tab === "deployment" ? (
            <>
              <p>
                {t("workflow.health")}: {model.active_endpoint?.health_status}
              </p>
              <code className="block break-all text-style-code-sm">
                {model.endpoint_url}
              </code>
              <RuntimeMetrics
                projectId={modelId!}
                deploymentId={model.active_endpoint?.deployment_id ?? ""}
              />
              <Suspense fallback={<p>{t("workflow.loading")}</p>}>
                <ModelTestingPage />
              </Suspense>
            </>
          ) : tab === "code" ? (
            source.isError ? (
              <p role="alert">{t("workflow.failed")}</p>
            ) : source.data ? (
              <LazyCodeEditor
                height="400px"
                language="python"
                theme={resolvedTheme === "dark" ? "vs-dark" : "light"}
                value={source.data}
                options={{ readOnly: true, minimap: { enabled: false } }}
              />
            ) : (
              <p>{t("workflow.noSource")}</p>
            )
          ) : reference.isError ? (
            <p role="alert">{t("workflow.failed")}</p>
          ) : reference.data ? (
            <DataViewer initialCsvText={reference.data} readOnly />
          ) : (
            <p>{t("workflow.noReference")}</p>
          )}
        </section>
      )}
      <ConfirmDialog
        open={deleting}
        title={t("workflow.delete")}
        description={t("workflow.deleteHint")}
        tone="danger"
        loading={remove.isPending}
        onConfirm={() => remove.mutate()}
        onCancel={() => setDeleting(false)}
      />
      {remove.isError && (
        <p role="alert">
          {getApiErrorMessage(remove.error, t("workflow.failed"))}
        </p>
      )}
      <EditMetadataDialog
        open={editMetadataOpen}
        onClose={() => setEditMetadataOpen(false)}
        project={{
          name: model.name,
          description: model.description,
          access_mode: model.access_mode,
        }}
        onSave={(payload) => update.mutateAsync(payload)}
        loading={update.isPending}
        error={update.error}
      />
    </div>
  );
}
