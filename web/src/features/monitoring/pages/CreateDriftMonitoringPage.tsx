import { useDriftMonitorForm } from "@/features/monitoring/hooks/useDriftMonitorForm";
import { productionPreview } from "@/features/monitoring/productionPreview";
import { getApiErrorMessage } from "@/shared/api/errors";
import { Badge } from "@/shared/components/Badge";
import { Button } from "@/shared/components/Button";
import { ConfirmDialog } from "@/shared/components/ConfirmDialog";
import { DataViewer } from "@/shared/components/DataViewer";
import { FileDropzone } from "@/shared/components/FileDropzone";
import { Loading } from "@/shared/components/Loading";
import { PageHeader } from "@/shared/components/PageHeader";
import { Placeholder } from "@/shared/components/Placeholder";
import { Select } from "@/shared/components/Select";
import { Slider } from "@/shared/components/Slider";
import { StepTitle } from "@/shared/components/StepTitle";
import { formatNumber } from "@/shared/i18n/formatters";
import { Database } from "lucide-react";
import Papa from "papaparse";
import { useEffect, useMemo, useRef, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import {
  useBlocker,
  useNavigate,
  useParams,
  useSearchParams,
} from "react-router-dom";

function CsvPreview({
  title,
  badge,
  text,
  loading,
  loadingText,
  error,
  empty,
  onRetry,
}: {
  title?: ReactNode;
  badge?: ReactNode;
  text?: string;
  loading: boolean;
  loadingText?: string;
  error: unknown;
  empty: string;
  onRetry: () => void;
}) {
  const { t } = useTranslation("monitoring");

  if (loading) {
    return (
      <Placeholder className="h-125 justify-center">
        <Loading size="lg" text={loadingText || t("loading")} />
      </Placeholder>
    );
  }

  if (error) {
    return (
      <Placeholder
        className="h-125 justify-center"
        icon={<Database className="h-8 w-8 text-color-danger" />}
        description={getApiErrorMessage(error, t("createPage.previewLoadFailed"))}
        action={
          <Button type="button" variant="secondary" onClick={onRetry}>
            {t("actions.retry")}
          </Button>
        }
      />
    );
  }

  if (!text) {
    return (
      <Placeholder
        className="h-125 justify-center"
        icon={<Database className="h-8 w-8" />}
        description={empty}
      />
    );
  }

  return (
    <div className="h-125 w-full overflow-hidden">
      <DataViewer
        key={text}
        title={title}
        badge={badge}
        initialCsvText={text}
        readOnly
      />
    </div>
  );
}

export default function CreateDriftMonitoringPage() {
  const { monitorId } = useParams();
  const [params, setParams] = useSearchParams();
  const projectId = params.get("projectId") || "";
  return (
    <CreateDriftMonitorContent
      key={`${monitorId ?? "new"}:${projectId}`}
      monitorId={monitorId}
      requestedProjectId={projectId}
      onSelectProject={(value) => setParams({ projectId: value })}
    />
  );
}

function CreateDriftMonitorContent({
  monitorId,
  requestedProjectId,
  onSelectProject,
}: {
  monitorId?: string;
  requestedProjectId: string;
  onSelectProject: (id: string) => void;
}) {
  const { t, i18n } = useTranslation("monitoring");
  const navigate = useNavigate();
  const saved = useRef(false);
  const form = useDriftMonitorForm(
    monitorId,
    requestedProjectId,
    (projectId) => {
      saved.current = true;
      navigate(`/dashboard/projects/${projectId}/monitoring`);
    },
  );
  const blocker = useBlocker(() => form.dirty && !saved.current);
  useEffect(() => {
    const handle = (event: BeforeUnloadEvent) => {
      if (form.dirty && !saved.current) event.preventDefault();
    };
    window.addEventListener("beforeunload", handle);
    return () => window.removeEventListener("beforeunload", handle);
  }, [form.dirty]);
  const productionCsv = useMemo(
    () =>
      form.production.data?.length
        ? Papa.unparse(productionPreview(form.production.data))
        : "",
    [form.production.data],
  );
  const error = form.save.error || form.error;
  const referenceName = monitorId
    ? form.existing.data?.reference_name
    : form.project.data?.reference_data?.name || form.reference?.name;

  const isReferenceLoading = Boolean(
    form.projectId && (form.project.isLoading || form.referenceQuery.isLoading),
  );
  const isProductionLoading = Boolean(
    form.projectId && (form.project.isLoading || form.production.isLoading),
  );

  return (
    <div className="space-y-6">
      <PageHeader
        title={t(monitorId ? "createPage.editTitle" : "createPage.createTitle")}
        back
      />
      <form
        className="space-y-6"
        onSubmit={(event) => {
          event.preventDefault();
          form.save.mutate();
        }}
      >
        <div className="space-y-6 rounded-surface border border-border bg-surface p-6">
          <Select
            value={form.projectId}
            disabled={Boolean(monitorId) || form.save.isPending}
            onChange={onSelectProject}
            placeholder={t("selectProject")}
            options={(form.projects.data?.models ?? [])
              .filter(
                (item) => item.active_endpoint?.deployment_status === "succeeded",
              )
              .map((item) => ({
                value: item.id,
                label: item.name,
                badge: (
                  <Badge variant="success" className="shrink-0">
                    {t("createPage.runningBadge")}
                  </Badge>
                ),
              }))}
          />
          <section className="space-y-4">
            <StepTitle
              title={t("createPage.referenceTitle")}
              description={t("referenceSnapshotHint")}
            />
            {form.projectId &&
            !form.project.isLoading &&
            !monitorId &&
            !form.hasReference ? (
              <FileDropzone
                accept=".csv"
                title={referenceName || t("createPage.referenceData")}
                subtitle={t("createPage.referenceUploadHint")}
                disabled={form.loading || !form.versionId || form.save.isPending}
                onChange={form.setReference}
              />
            ) : null}
            {form.fileError && (
              <p role="alert" className="text-color-danger">
                {form.fileError}
              </p>
            )}
            <CsvPreview
              title={referenceName || "reference_data.csv"}
              badge={<Badge variant="info">{t("createPage.referenceDataBadge")}</Badge>}
              text={form.referenceQuery.data}
              loading={isReferenceLoading}
              loadingText={t("createPage.loadingReferenceData")}
              error={form.referenceQuery.error}
              empty={
                !form.projectId
                  ? t("createPage.selectProjectToViewReference")
                  : t("createPage.referenceRequired")
              }
              onRetry={() => void form.referenceQuery.refetch()}
            />
          </section>
          <section className="space-y-4 border-t border-border pt-6">
            <StepTitle
              title={t("createPage.thresholdTitle")}
              description={t("createPage.thresholdDescription")}
            />
            <div className="px-4 pt-4 pb-4">
              <Slider
                ariaLabel={t("trigger")}
                disabled={!form.projectId || form.save.isPending}
                options={form.allowedThresholds.map((value) => ({
                  value,
                  label: formatNumber(
                    value,
                    i18n.resolvedLanguage || i18n.language,
                  ),
                }))}
                value={form.triggerThreshold}
                onChange={form.setThreshold}
                getColor={(_index, value) =>
                  value >= 20000
                    ? "bg-danger"
                    : value >= 5000
                      ? "bg-warning"
                      : "bg-success"
                }
              />
            </div>
          </section>
          <section className="space-y-4 border-t border-border pt-6">
            <StepTitle
              title={t("createPage.previewTitle")}
              description={t("createPage.previewDescription")}
            />
            <CsvPreview
              title={<Badge variant="info">{t("createPage.productionDataBadge")}</Badge>}
              text={productionCsv}
              loading={isProductionLoading}
              loadingText={t("createPage.loadingProduction")}
              error={form.production.error}
              empty={
                !form.projectId
                  ? t("createPage.selectProjectToViewProduction")
                  : t("createPage.productionEmpty")
              }
              onRetry={() => void form.production.refetch()}
            />
          </section>
          {Boolean(error) && (
            <p role="alert" className="text-color-danger">
              {getApiErrorMessage(error, t("createPage.saveFailed"))}
            </p>
          )}
        </div>

        <div className="grid grid-cols-2 gap-4">
          <Button
            type="button"
            variant="secondary"
            fullWidth
            disabled={form.save.isPending}
            onClick={() =>
              navigate(
                form.projectId
                  ? `/dashboard/projects/${form.projectId}/monitoring`
                  : "/dashboard/monitoring",
              )
            }
          >
            {t("actions.cancel")}
          </Button>
          <Button
            type="submit"
            fullWidth
            loading={form.save.isPending}
            disabled={!form.canSave || form.save.isPending}
          >
            {t(monitorId ? "createPage.update" : "createPage.create")}
          </Button>
        </div>

        <div className="h-0.5 shrink-0" aria-hidden="true" />
      </form>
      <ConfirmDialog
        open={blocker.state === "blocked"}
        title={t("unsaved")}
        description={t("leaveHint")}
        onConfirm={() => blocker.state === "blocked" && blocker.proceed()}
        onCancel={() => blocker.state === "blocked" && blocker.reset()}
      />
    </div>
  );
}
