import { useDriftMonitorForm } from "@/features/monitoring/hooks/useDriftMonitorForm";
import { productionPreview } from "@/features/monitoring/productionPreview";
import { getApiErrorMessage } from "@/shared/api/errors";
import { Button } from "@/shared/components/Button";
import { ConfirmDialog } from "@/shared/components/ConfirmDialog";
import { DataViewer } from "@/shared/components/DataViewer";
import { FileDropzone } from "@/shared/components/FileDropzone";
import { PageHeader } from "@/shared/components/PageHeader";
import { Select } from "@/shared/components/Select";
import { Slider } from "@/shared/components/Slider";
import { StepTitle } from "@/shared/components/StepTitle";
import { formatNumber } from "@/shared/i18n/formatters";
import { Database } from "lucide-react";
import Papa from "papaparse";
import { useEffect, useMemo, useRef } from "react";
import { useTranslation } from "react-i18next";
import {
  useBlocker,
  useNavigate,
  useParams,
  useSearchParams,
} from "react-router-dom";

function CsvPreview({
  text,
  loading,
  error,
  empty,
  onRetry,
}: {
  text?: string;
  loading: boolean;
  error: unknown;
  empty: string;
  onRetry: () => void;
}) {
  const { t } = useTranslation("monitoring");
  const isParquet = text === "PARQUET_PREVIEW";
  return (
    <div className="h-100 overflow-hidden rounded-surface border border-border bg-muted">
      {isParquet ? (
        <div className="flex h-full flex-col items-center justify-center gap-3 p-4 text-center text-color-muted-foreground">
          <Database className="h-8 w-8 text-color-primary" />
          <p className="text-style-body font-medium text-color-foreground">
            {t("createPage.parquetStagedTitle")}
          </p>
          <p className="max-w-md text-style-caption">
            {t("createPage.parquetStagedDesc")}
          </p>
        </div>
      ) : text && !error ? (
        <DataViewer key={text} initialCsvText={text} readOnly />
      ) : (
        <div className="flex h-full flex-col items-center justify-center gap-3 p-4 text-center text-color-muted-foreground">
          <Database className="h-8 w-8" />
          <p role={error ? "alert" : undefined}>
            {loading
              ? t("loading")
              : error
                ? getApiErrorMessage(error, t("createPage.previewLoadFailed"))
                : empty}
          </p>
          {Boolean(error) && (
            <Button type="button" variant="secondary" onClick={onRetry}>
              {t("actions.retry")}
            </Button>
          )}
        </div>
      )}
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
  return (
    <div className="space-y-6">
      <PageHeader
        title={t(monitorId ? "createPage.editTitle" : "createPage.createTitle")}
        back
      />
      <form
        className="space-y-6 rounded-surface border border-border bg-surface p-6"
        onSubmit={(event) => {
          event.preventDefault();
          form.save.mutate();
        }}
      >
        <Select
          value={form.projectId}
          disabled={Boolean(monitorId) || form.save.isPending}
          onChange={onSelectProject}
          placeholder={t("selectProject")}
          options={(form.projects.data?.models ?? [])
            .filter(
              (item) => item.active_endpoint?.deployment_status === "succeeded",
            )
            .map((item) => ({ value: item.id, label: item.name }))}
        />
        <section className="space-y-4">
          <StepTitle
            title={t("createPage.referenceTitle")}
            description={t("referenceSnapshotHint")}
          />
          {monitorId || form.hasReference ? (
            <div className="space-y-2">
              <p className="text-style-body-strong">{referenceName}</p>
              <p className="text-color-muted-foreground">
                {t(
                  monitorId
                    ? "createPage.monitorReferenceLocked"
                    : "usingVersionReference",
                )}
              </p>
            </div>
          ) : (
            <FileDropzone
              accept=".csv,.parquet"
              title={referenceName || t("createPage.referenceData")}
              subtitle={t("createPage.referenceUploadHint")}
              disabled={form.loading || !form.versionId || form.save.isPending}
              onChange={form.setReference}
            />
          )}
          {form.fileError && (
            <p role="alert" className="text-color-danger">
              {form.fileError}
            </p>
          )}
          <CsvPreview
            text={form.referenceQuery.data}
            loading={form.referenceQuery.isLoading}
            error={form.referenceQuery.error}
            empty={t("createPage.referenceRequired")}
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
              disabled={form.save.isPending}
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
            text={productionCsv}
            loading={form.production.isLoading}
            error={form.production.error}
            empty={t("createPage.productionEmpty")}
            onRetry={() => void form.production.refetch()}
          />
        </section>
        {Boolean(error) && (
          <p role="alert" className="text-color-danger">
            {getApiErrorMessage(error, t("createPage.saveFailed"))}
          </p>
        )}
        <div className="flex flex-wrap gap-3 border-t border-border pt-6">
          <Button
            type="button"
            variant="secondary"
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
            loading={form.save.isPending}
            disabled={!form.canSave || form.save.isPending}
          >
            {t(monitorId ? "createPage.update" : "createPage.create")}
          </Button>
        </div>
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
