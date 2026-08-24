import { AlertTriangle, RefreshCw, History } from "lucide-react";
import { useTranslation } from "react-i18next";

import { TrainingEventHistory } from "@/features/training/components/TrainingOverviewSections";
import { useTrainingJobDetailContext } from "@/features/training/trainingJobDetailContext";
import { Button } from "@/shared/components/Button";
import { PageBody } from "@/shared/components/PageBody";
import { TerminalViewer } from "@/shared/components/TerminalViewer";

export default function TrainingJobLogsPage() {
  const { t } = useTranslation("training");
  const {
    job,
    activeStatuses,
    logsResponse,
    loadingLogs,
    eventsResponse,
    refreshingSection,
    refreshLogs,
  } = useTrainingJobDetailContext();

  return (
    <div className="animate-in space-y-4 fade-in duration-300">
      {job.status === "failed" && job.stop_reason && (
        <div className="flex items-start gap-3 rounded-surface border border-danger/20 bg-danger-subtle p-4 text-style-body-strong text-color-danger">
          <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-color-danger" />
          <div>
            <p className="mb-1 font-bold text-color-danger">{t("detail.logsPage.stopReason")}</p>
            <p>{job.stop_reason}</p>
          </div>
        </div>
      )}
      <TerminalViewer
        title={t("detail.logsPage.title")}
        bodyClassName="min-h-100 max-h-150"
        actions={
          <Button
            variant="secondary"
            size="sm"
            onClick={() => void refreshLogs()}
            disabled={loadingLogs || refreshingSection === "logs"}
            icon={
              <RefreshCw
                className={`h-3 w-3 ${
                  loadingLogs || refreshingSection === "logs"
                    ? "animate-spin"
                    : ""
                }`}
              />
            }
          >
            {t("detail.logsPage.refresh")}
          </Button>
        }
        logs={
          logsResponse?.text
            ? logsResponse.text.split("\n")
            : activeStatuses.includes(job.status)
              ? [t("detail.logsPage.waiting")]
              : [t("detail.logsPage.empty")]
        }
      />

      <PageBody
        title={
          <div className="flex items-center gap-2">
            <History className="h-5 w-5" />
            <h3 className="text-style-heading">{t("detail.logsPage.events")}</h3>
          </div>
        }
        className="mt-8"
      >
        <div className="p-6">
          <TrainingEventHistory events={eventsResponse?.events || []} />
        </div>
      </PageBody>
    </div>
  );
}
