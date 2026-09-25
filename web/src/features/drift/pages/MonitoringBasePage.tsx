import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { getProjectVersions } from "@/features/deploy/api/deployApi";
import type { ModelVersion } from "@/features/catalog/types";
import { PageHeader } from "@/shared/components/PageHeader";
import { Badge } from "@/shared/components/Badge";
import { Button } from "@/shared/components/Button";
import { projectPaths } from "@/app/router/paths";

export default function MonitoringBasePage() {
  const { projectId = "" } = useParams<{ projectId: string }>();
  const navigate = useNavigate();
  const { t } = useTranslation("drift");
  const [versions, setVersions] = useState<ModelVersion[]>([]);
  const [versionId, setVersionId] = useState("");
  const version = versions.find((item) => item.id === versionId) ?? versions[0];
  useEffect(() => { void getProjectVersions(projectId).then((result) => { setVersions(result); setVersionId(result.find((item) => item.aliases.includes("production"))?.id ?? result[0]?.id ?? ""); }); }, [projectId]);
  const reference = version?.artifacts.find((item) => item.kind === "reference_data");
  return <section className="space-y-6"><PageHeader title={t("workflow.baselineTitle")} description={t("workflow.baselineDescription")} /><div className="max-w-xl space-y-5 rounded-surface border border-border bg-surface p-6"><label className="block space-y-2 text-style-body-strong">{t("workflow.modelVersion")}<select className="block w-full rounded-surface border border-border bg-surface px-3 py-2" value={version?.id ?? ""} onChange={(event) => setVersionId(event.target.value)}>{versions.map((item) => <option key={item.id} value={item.id}>{"v" + item.version}{item.aliases.includes("production") ? ` ${t("workflow.production")}` : ""}</option>)}</select></label>{version ? <div className="space-y-3 rounded-surface bg-muted/30 p-4"><div className="flex justify-between"><strong>{t("workflow.version", { version: version.version })}</strong><Badge variant="success">{t("workflow.immutable")}</Badge></div><p className="text-style-caption text-color-muted-foreground">{t("workflow.referenceData")} {reference?.name ?? t("workflow.noArtifact")}</p>{reference && <p className="break-all font-mono text-style-caption text-color-muted-foreground">{t("workflow.checksum")} {reference.checksum || t("workflow.notRecorded")}</p>}<p className="text-style-caption text-color-muted-foreground">{t("workflow.baselineFixed")}</p></div> : <p>{t("workflow.noVersions")}</p>}<Button variant="secondary" onClick={() => navigate(projectPaths.monitoring(projectId))}>{t("workflow.openMonitoring")}</Button></div></section>;
}
