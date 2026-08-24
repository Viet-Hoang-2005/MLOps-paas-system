import { MetadataRow } from "@/features/training/components/TrainingOverviewSections";
import { useTrainingJobDetailContext } from "@/features/training/trainingJobDetailContext";
import { useTranslation } from "react-i18next";

export default function TrainingJobConfigPage() {
  const { t } = useTranslation("training");
  const { job } = useTrainingJobDetailContext();

  return (
    <div className="animate-in overflow-hidden rounded-surface border border-border bg-surface shadow-sm fade-in duration-300">
      <div className="border-b border-border bg-muted/50 px-6 py-4">
        <h3 className="text-style-overline uppercase text-color-foreground">
          {t("detail.config.title")}
        </h3>
      </div>
      <div className="space-y-8 p-6">
        <div>
          <h4 className="mb-4 border-b border-border pb-2 text-style-overline uppercase text-color-muted-foreground">
            {t("detail.config.compute")}
          </h4>
          <div className="grid grid-cols-1 gap-x-8 gap-y-6 sm:grid-cols-2 lg:grid-cols-3">
            <MetadataRow
              label={t("detail.config.backend")}
              value={job.backend || t("statuses.unknown", { ns: "common" })}
            />
            <MetadataRow label={t("detail.config.vcpu")} value={String(job.vcpu)} />
            <MetadataRow label={t("detail.config.memory")} value={String(job.memory)} />
            <MetadataRow
              label={t("detail.config.maxRuntime")}
              value={String(job.max_runtime_seconds)}
            />
          </div>
        </div>
        <div>
          <h4 className="mb-4 border-b border-border pb-2 text-style-overline uppercase text-color-muted-foreground">
            {t("detail.config.accelerator")}
          </h4>
          <div className="grid grid-cols-1 gap-x-8 gap-y-6 sm:grid-cols-2 lg:grid-cols-3">
            <MetadataRow
              label={t("detail.config.acceleratorType")}
              value={
                job.accelerator_type === "none"
                  ? t("statuses.none", { ns: "common" })
                  : job.accelerator_type.toUpperCase()
              }
            />
            {job.accelerator_type !== "none" && (
              <MetadataRow
                label={t("detail.config.acceleratorCount")}
                value={String(job.accelerator_count)}
              />
            )}
          </div>
        </div>
        <div>
          <h4 className="mb-4 border-b border-border pb-2 text-style-overline uppercase text-color-muted-foreground">
            {t("detail.config.source")}
          </h4>
          <MetadataRow
            label={t("detail.config.entryPoint")}
            value={job.entry_point}
            monospace
          />
        </div>
      </div>
    </div>
  );
}
