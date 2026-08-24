import React, { useMemo, useState } from "react";
import Papa from "papaparse";
import { useParams, useNavigate } from "react-router-dom";
import { Database } from "lucide-react";
import { Slider } from "@/shared/components/Slider";
import { PageHeader } from "@/shared/components/PageHeader";
import { Button } from "@/shared/components/Button";
import { CSVEditor } from "@/shared/components/CSVEditor";
import { SourceEditor } from "@/features/catalog/components/SourceEditor";
import { StepTitle } from "@/shared/components/StepTitle";
import {
  useCreateDriftMonitoringJob,
  useDriftMonitoringJobs,
  useProductionData,
  useUpdateDriftMonitoringJob,
} from "@/features/drift/hooks/useDriftMonitoring";
import { getApiErrorMessage } from "@/shared/api/errors";
import { toast } from "@/shared/components/toastStore";
import { useTranslation } from "react-i18next";

const THRESHOLD_MARKS = [
  { value: 500, label: "500" },
  { value: 1000, label: "1000" },
  { value: 2000, label: "2000" },
  { value: 5000, label: "5000" },
  { value: 10000, label: "10K" },
  { value: 20000, label: "20K" },
];

const DataPlaceholder = ({
  title,
  action,
}: {
  title: string;
  action?: React.ReactNode;
}) => (
  <div className="flex h-full flex-col items-center justify-center gap-2 text-color-muted-foreground">
    <Database className="w-8 h-8 text-color-muted-foreground" />
    <p>{title}</p>
    {action}
  </div>
);

export default function CreateDriftMonitoringPage() {
  const { modelId } = useParams<{ modelId: string }>();
  const navigate = useNavigate();
  const { t } = useTranslation("drift");

  const [selectedReferencePath, setSelectedReferencePath] = useState<
    string | null
  >(null);
  const [selectedTriggerThreshold, setSelectedTriggerThreshold] = useState<
    number | null
  >(null);
  const { data: monitors, isLoading: isLoadingMonitors } =
    useDriftMonitoringJobs(modelId);
  const existingMonitor = useMemo(
    () => monitors?.find((monitor) => monitor.is_active),
    [monitors],
  );

  const {
    data: productionLogs,
    isLoading: isLoadingProductionData,
    isError: isProductionDataError,
    refetch: refetchProductionData,
  } = useProductionData(modelId);
  const { mutateAsync: createJob, isPending: isSubmitting } =
    useCreateDriftMonitoringJob();
  const { mutateAsync: updateJob, isPending: isUpdating } =
    useUpdateDriftMonitoringJob();
  const referencePath =
    selectedReferencePath ?? existingMonitor?.reference_asset_name ?? "";
  const triggerThreshold =
    selectedTriggerThreshold ?? existingMonitor?.trigger_threshold ?? 1000;

  // Convert production logs (features + prediction) to CSV for preview
  // Each row: spread all feature key-value pairs + prediction column
  const productionCsv = React.useMemo(() => {
    if (!productionLogs || productionLogs.length === 0) return "";

    const rows = productionLogs.map((log) => {
      let features: Record<string, unknown> = {};
      if (log.features) {
        if (typeof log.features === "string") {
          try {
            features = JSON.parse(log.features);
          } catch {
            features = {};
          }
        } else if (typeof log.features === "object") {
          features = log.features as Record<string, unknown>;
        }
      }
      return { ...features, prediction: log.prediction };
    });

    return Papa.unparse(rows);
  }, [productionLogs]);

  const handleSubmit = async () => {
    if (!referencePath) {
      toast.error(t("createPage.referenceRequired"));
      return;
    }
    try {
      const payload = {
        project_id: modelId!,
        trigger_threshold: triggerThreshold,
        reference_data_s3_path: referencePath,
      };
      if (existingMonitor) {
        await updateJob({ ...payload, id: existingMonitor.id });
      } else {
        await createJob(payload);
      }
      toast.success(
        existingMonitor
          ? t("createPage.updated")
          : t("createPage.created"),
      );
      navigate(`/dashboard/drift-monitoring/${modelId}`);
    } catch (err) {
      const msg = getApiErrorMessage(err, t("createPage.saveFailed"));
      toast.error(msg);
    }
  };

  const isSaving = isSubmitting || isUpdating;

  return (
    <div className="flex w-full flex-1 flex-col space-y-6">
      <PageHeader
        title={
          existingMonitor ? t("createPage.editTitle") : t("createPage.createTitle")
        }
        backLink={{
          label: t("createPage.back"),
          to: `/dashboard/drift-monitoring/${modelId}`,
        }}
      />
      <section className="flex flex-col flex-1 rounded-surface border border-border bg-surface p-6 space-y-6">
        <div className="space-y-4">
          <StepTitle
            title={t("createPage.referenceTitle")}
            description={t("createPage.referenceDescription")}
          />
          <SourceEditor
            modelId={modelId!}
            fileType="data_file"
            title={t("createPage.referenceData")}
            icon={<Database className="w-4 h-4" />}
            accept=".csv"
            editorType="csv"
            currentEntryPoint={referencePath}
            onSetEntryPoint={setSelectedReferencePath}
            entryPointExtension=".csv"
            setAsMainLabel={t("createPage.setReference")}
          />
        </div>

        <div className="space-y-4 border-t border-border pt-6">
          <StepTitle
            title={t("createPage.thresholdTitle")}
            description={t("createPage.thresholdDescription")}
          />
          <div className="px-8 pb-4">
            <Slider
              options={THRESHOLD_MARKS}
              value={triggerThreshold}
              onChange={(val) => setSelectedTriggerThreshold(val)}
              getColor={(index) => {
                if (index >= 5) return "bg-danger";
                if (index >= 3) return "bg-warning";
                return "bg-success";
              }}
            />
          </div>
        </div>

        <div className="space-y-4 border-t border-border pt-6">
          <StepTitle
            title={t("createPage.previewTitle")}
            description={t("createPage.previewDescription")}
          />
          <div className="h-100 rounded-surface border border-border overflow-hidden relative bg-muted">
            {isLoadingProductionData ? (
              <div className="flex h-full items-center justify-center text-color-muted-foreground">
                {t("createPage.loadingProduction")}
              </div>
            ) : isProductionDataError ? (
              <DataPlaceholder
                title={t("createPage.productionLoadFailed")}
                action={
                  <Button
                    variant="secondary"
                    size="md"
                    onClick={() => void refetchProductionData()}
                  >
                    {t("actions.retry", { ns: "common" })}
                  </Button>
                }
              />
            ) : productionCsv ? (
              <CSVEditor initialCsvText={productionCsv} readOnly={true} />
            ) : (
              <DataPlaceholder title={t("createPage.productionEmpty")} />
            )}
          </div>
        </div>

        <div className="flex items-center gap-4 border-t border-border pt-6">
          <Button
            variant="secondary"
            size="md"
            className="flex-1"
            onClick={() => navigate(`/dashboard/drift-monitoring/${modelId}`)}
            disabled={isSaving}
          >
            {t("actions.cancel", { ns: "common" })}
          </Button>
          <Button
            variant="primary"
            size="md"
            className="flex-1"
            onClick={handleSubmit}
            disabled={isSaving || isLoadingMonitors || !referencePath}
          >
            {isSaving
              ? t("createPage.saving")
              : existingMonitor
                ? t("createPage.update")
                : t("createPage.create")}
          </Button>
        </div>
      </section>
    </div>
  );
}
