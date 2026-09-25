import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { getProjectVersions } from "@/features/deploy/api/deployApi";
import type { ModelVersion } from "@/features/catalog/types";
import { useCreateDriftMonitoringJob, useDriftMonitoringJobs, useUpdateDriftMonitoringJob } from "@/features/drift/hooks/useDriftMonitoring";
import { PageHeader } from "@/shared/components/PageHeader";
import { Button } from "@/shared/components/Button";
import { toast } from "@/shared/components/toastStore";
import { getApiErrorMessage } from "@/shared/api/errors";
import { projectPaths } from "@/app/router/paths";

export default function CreateDriftMonitoringPage() {
  const { projectId = "" } = useParams<{ projectId: string }>();
  const navigate = useNavigate();
  const { t } = useTranslation("drift");
  const [versions, setVersions] = useState<ModelVersion[]>([]);
  const [versionId, setVersionId] = useState("");
  const [threshold, setThreshold] = useState(1000);
  const { data: monitors = [] } = useDriftMonitoringJobs(projectId);
  const current = monitors.find((monitor) => monitor.is_active);
  const create = useCreateDriftMonitoringJob();
  const update = useUpdateDriftMonitoringJob();
  useEffect(() => { void getProjectVersions(projectId).then((result) => { setVersions(result); setVersionId(current?.version_id ?? result.find((item) => item.aliases.includes("production"))?.id ?? result[0]?.id ?? ""); }); }, [current?.version_id, projectId]);
  const version = versions.find((item) => item.id === versionId);
  const save = async () => {
    if (!version || !version.artifacts.some((item) => item.kind === "reference_data")) { toast.warning(t("workflow.chooseVersion")); return; }
    try {
      const payload = { project_id: projectId, version_id: version.id, trigger_threshold: threshold };
      if (current) await update.mutateAsync({ ...payload, id: current.id });
      else await create.mutateAsync(payload);
      toast.success(t("workflow.saved"));
      navigate(projectPaths.monitoring(projectId));
    } catch (error) { toast.error(getApiErrorMessage(error, t("workflow.saveFailed"))); }
  };
  return <section className="mx-auto max-w-2xl space-y-6"><PageHeader title={current ? t("workflow.configureTitle") : t("workflow.createTitle")} description={t("workflow.description")} /><div className="space-y-5 rounded-surface border border-border bg-surface p-6"><label className="block space-y-2 text-style-body-strong">{t("workflow.modelVersion")}<select className="block w-full rounded-surface border border-border bg-surface px-3 py-2" value={versionId} onChange={(event) => setVersionId(event.target.value)}>{versions.map((item) => <option key={item.id} value={item.id}>{"v" + item.version}{item.aliases.includes("production") ? ` ${t("workflow.production")}` : ""}</option>)}</select></label><div className="rounded-surface bg-muted/30 p-4 text-style-body">{t("workflow.referenceData")} {version?.artifacts.find((item) => item.kind === "reference_data")?.name ?? t("workflow.noBaseline")}<p className="mt-1 text-style-caption text-color-muted-foreground">{t("workflow.fixedNote")}</p></div><label className="block space-y-2 text-style-body-strong">{t("workflow.threshold")}<input className="block w-full rounded-surface border border-border bg-surface px-3 py-2" type="number" min={1} value={threshold} onChange={(event) => setThreshold(Number(event.target.value))} /></label><div className="flex justify-end gap-2"><Button variant="secondary" onClick={() => navigate(projectPaths.monitoring(projectId))}>{t("workflow.cancel")}</Button><Button variant="primary" loading={create.isPending || update.isPending} onClick={() => void save()}>{t("workflow.saveMonitor")}</Button></div></div></section>;
}
