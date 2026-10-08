import { RouteFallback } from "@/app/router/RouteFallback";
import { useTheme } from "@/app/theme/useTheme";
import {
  useProjectOverview,
  useRunningAttributes,
  useRunningSource,
  useSnapshotText,
} from "@/features/overview/hooks/useProjectOverview";
import { AttributesOverviewPage } from "@/features/overview/pages/AttributesOverviewPage";
import { CodeOverviewPage } from "@/features/overview/pages/CodeOverviewPage";
import { DataOverviewPage } from "@/features/overview/pages/DataOverviewPage";
import { DeploymentOverviewPage } from "@/features/overview/pages/DeploymentOverviewPage";
import { InformationOverviewPage } from "@/features/overview/pages/InformationOverviewPage";
import { EditMetadataDialog } from "@/features/projects/components/EditMetadataDialog";
import { NoProjectPlaceholder } from "@/features/projects/components/NoProjectPlaceholder";
import { useModelSelection } from "@/features/projects/hooks/useModelSelection";
import { usePreview } from "@/features/projects/hooks/usePreview";
import { catalogQueryKeys } from "@/features/projects/queryKeys";
import {
  deleteModelProject,
  updateModelProject,
} from "@/shared/api/catalogApi";
import { getApiErrorMessage } from "@/shared/api/errors";
import { Badge } from "@/shared/components/Badge";
import { Button } from "@/shared/components/Button";
import { ConfirmDialog } from "@/shared/components/ConfirmDialog";
import { PageHeader } from "@/shared/components/PageHeader";
import { PageTabs } from "@/shared/components/PageTabs";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Box,
  Code,
  FileSpreadsheet,
  Home,
  Info,
  PenLine,
  Settings2,
  SlidersHorizontal,
  Trash2,
} from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import {
  Navigate,
  useNavigate,
  useParams,
  useSearchParams,
} from "react-router-dom";

export default function ProjectOverviewPage() {
  const { modelId } = useParams();
  const { t } = useTranslation("overview");
  const { t: tCommon } = useTranslation("common");
  const { selectedModel, loading: isModelLoading } = useModelSelection();
  const { resolvedTheme } = useTheme();
  const navigate = useNavigate();
  const client = useQueryClient();
  const [params, setParams] = useSearchParams();
  const tab = params.get("tab") || "deployment";
  const project = useProjectOverview(modelId);
  const model = project.data;
  const hasRunning = model?.active_endpoint?.deployment_status === "succeeded";
  const isPreview = Boolean(model) && !hasRunning;
  const effectiveVersionId = hasRunning ? model?.active_endpoint?.version_id : undefined;

  const source = useRunningSource(
    hasRunning && tab === "code" ? modelId : undefined,
    effectiveVersionId,
  );
  const reference = useSnapshotText(
    hasRunning && tab === "data" ? model?.reference_data?.download_url : undefined,
    effectiveVersionId,
  );
  const attributes = useRunningAttributes(
    modelId,
    effectiveVersionId,
    isPreview,
  );

  const preview = usePreview(isPreview ? modelId : undefined);
  const previewSourceAsset = preview.data?.assets.find(
    (a) => a.kind === "source_code",
  );
  const previewRefAsset = preview.data?.assets.find(
    (a) => a.kind === "reference_data",
  );
  const previewSource = useSnapshotText(
    isPreview && tab === "code" ? previewSourceAsset?.download_url : undefined,
    isPreview && previewSourceAsset
      ? `preview-source-${modelId}-${preview.data?.revision}`
      : undefined,
  );
  const previewReference = useSnapshotText(
    isPreview && tab === "data" ? previewRefAsset?.download_url : undefined,
    isPreview && previewRefAsset
      ? `preview-ref-${modelId}-${preview.data?.revision}`
      : undefined,
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

  if (project.isError && !model)
    return (
      <p role="alert">
        {getApiErrorMessage(project.error, t("workflow.failed"))}
      </p>
    );

  if (!model) return <p>{t("workflow.loading")}</p>;

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
              {!hasRunning && model.lifecycle_status === "registered" && (
                <Badge variant="neutral">{t("workflow.preview")}</Badge>
              )}
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
              label: t("workflow.attributes"),
              icon: SlidersHorizontal,
              isActive: tab === "attributes",
              onClick: () => setParams({ tab: "attributes" }),
            },
            {
              label: t("workflow.code"),
              icon: Code,
              isActive: tab === "code",
              onClick: () => setParams({ tab: "code" }),
            },
            {
              label: t("workflow.data"),
              icon: FileSpreadsheet,
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

      {tab === "deployment" && (
        <DeploymentOverviewPage
          model={model}
          modelId={modelId!}
          hasRunning={hasRunning}
          healthUnavailable={project.isError}
        />
      )}

      {tab === "attributes" && (
        <AttributesOverviewPage
          modelId={modelId!}
          effectiveVersionId={effectiveVersionId}
          isPreview={isPreview}
          attributes={attributes.data}
          isLoading={attributes.isLoading}
          isError={attributes.isError}
          onRetry={() => attributes.refetch()}
        />
      )}

      {tab === "code" && (
        <CodeOverviewPage
          modelId={modelId!}
          effectiveVersionId={effectiveVersionId}
          isPreview={isPreview}
          source={{
            data: source.data,
            isLoading: source.isLoading,
            isError: source.isError,
          }}
          previewSource={{
            asset: previewSourceAsset,
            data: previewSource.data,
            isLoading:
              preview.isLoading ||
              (Boolean(previewSourceAsset) && previewSource.isLoading),
            isError: previewSource.isError,
          }}
          theme={resolvedTheme}
          onUploadSuccess={async () => {
            if (isPreview) {
              await preview.refetch();
              await project.refetch();
            } else {
              await project.refetch();
              await source.refetch();
            }
          }}
        />
      )}

      {tab === "data" && (
        <DataOverviewPage
          modelId={modelId!}
          effectiveVersionId={effectiveVersionId}
          isPreview={isPreview}
          referenceDataName={model.reference_data?.name}
          reference={{
            data: reference.data,
            isLoading: reference.isLoading,
            isError: reference.isError,
          }}
          previewReference={{
            asset: previewRefAsset,
            data: previewReference.data,
            isLoading:
              preview.isLoading ||
              (Boolean(previewRefAsset) && previewReference.isLoading),
            isError: previewReference.isError,
          }}
          onUploadSuccess={async () => {
            if (isPreview) {
              await preview.refetch();
              await project.refetch();
            } else {
              await project.refetch();
              await reference.refetch();
            }
          }}
        />
      )}

      {tab === "information" && (
        <InformationOverviewPage
          model={model}
          onUpdateAccessMode={(accessMode) =>
            update.mutate({
              name: model.name,
              description: model.description,
              access_mode: accessMode,
            })
          }
        />
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
