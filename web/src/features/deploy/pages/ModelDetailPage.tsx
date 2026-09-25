import { useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useLocation, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Hammer, Rocket } from "lucide-react";
import { buildDraft } from "@/features/catalog/api/draftApi";
import { deployBuild, getProjectVersions, listDeployments, listProjectBuilds } from "@/features/deploy/api/deployApi";
import { projectPaths } from "@/app/router/paths";
import { Button } from "@/shared/components/Button";
import { Badge } from "@/shared/components/Badge";
import { PageHeader } from "@/shared/components/PageHeader";
import { toast } from "@/shared/components/toastStore";
import { getApiErrorMessage } from "@/shared/api/errors";

export default function ModelDetailPage() {
  const { projectId = "" } = useParams<{ projectId: string }>();
  const location = useLocation();
  const { t } = useTranslation("deploy");
  const queryClient = useQueryClient();
  const [versionId, setVersionId] = useState("");
  const [target, setTarget] = useState<"staging" | "production">("staging");
  const [busy, setBusy] = useState(false);
  const buildsQuery = useQuery({ queryKey: ["project-builds", projectId], queryFn: () => listProjectBuilds(projectId), refetchInterval: 5000 });
  const versionsQuery = useQuery({ queryKey: ["project-versions", projectId], queryFn: () => getProjectVersions(projectId) });
  const deploymentsQuery = useQuery({ queryKey: ["deployments"], queryFn: listDeployments, refetchInterval: 5000 });
  const versions = useMemo(() => versionsQuery.data ?? [], [versionsQuery.data]);
  const builds = buildsQuery.data ?? [];
  const deployments = (deploymentsQuery.data ?? []).filter((item) => item.project_id === projectId);
  const images = useMemo(() => versions.filter((item) => item.artifacts.some((artifact) => artifact.kind === "image")), [versions]);
  const latestDraftBuild = builds.find((item) => item.source_kind === "draft");
  const requestedBuildId = (location.state as { buildId?: string } | null)?.buildId;

  const buildFromDraft = async () => {
    setBusy(true);
    try {
      await buildDraft(projectId);
      await queryClient.invalidateQueries({ queryKey: ["project-builds", projectId] });
      toast.success(t("uploadFlow.messages.workflowPage.buildQueued"));
    } catch (error) { toast.error(getApiErrorMessage(error, t("uploadFlow.messages.workflowPage.buildFailed"))); }
    finally { setBusy(false); }
  };

  const deployVersion = async () => {
    if (!versionId) { toast.warning(t("uploadFlow.messages.workflowPage.chooseVersion")); return; }
    setBusy(true);
    try {
      await deployBuild(versionId, target);
      await queryClient.invalidateQueries({ queryKey: ["deployments"] });
      toast.success(`${target} deployment was queued. The alias changes after health checks pass.`);
    } catch (error) { toast.error(getApiErrorMessage(error, t("uploadFlow.messages.workflowPage.deployFailed"))); }
    finally { setBusy(false); }
  };

  return (
    <section className="space-y-6">
      <PageHeader title={t("uploadFlow.messages.workflowPage.title")} description={t("uploadFlow.messages.workflowPage.description")} />
      <div className="grid gap-6 lg:grid-cols-2">
        <section className="space-y-4 rounded-surface border border-border bg-surface p-6"><div className="flex items-center gap-2"><Hammer className="h-5 w-5 text-color-primary" /><h2 className="text-style-section-title">{t("uploadFlow.messages.workflowPage.buildDraft")}</h2></div><p className="text-style-body text-color-muted-foreground">{t("uploadFlow.messages.workflowPage.draftDescription")}</p><div className="rounded-surface bg-muted/40 p-4"><div className="flex justify-between"><span>{t("uploadFlow.messages.workflowPage.latestDraftBuild")}</span><Badge variant={latestDraftBuild?.status === "ready" ? "success" : latestDraftBuild?.status === "failed" ? "danger" : "neutral"}>{requestedBuildId && latestDraftBuild?.id === requestedBuildId ? latestDraftBuild.status : latestDraftBuild?.status ?? t("uploadFlow.messages.workflowPage.noBuild")}</Badge></div>{latestDraftBuild?.error_message && <p className="mt-2 text-style-caption text-color-danger">{latestDraftBuild.error_message}</p>}</div><div className="flex gap-3"><Button variant="primary" disabled={busy} loading={busy} onClick={() => void buildFromDraft()}>{t("uploadFlow.messages.workflowPage.buildSavedRevision")}</Button><Link className="inline-flex items-center rounded-surface border border-border px-3 text-style-caption" to={projectPaths.overviewDraft(projectId)}>{t("uploadFlow.messages.workflowPage.editDraft")}</Link></div></section>
        <section className="space-y-4 rounded-surface border border-border bg-surface p-6"><div className="flex items-center gap-2"><Rocket className="h-5 w-5 text-color-primary" /><h2 className="text-style-section-title">{t("uploadFlow.messages.workflowPage.deployVersion")}</h2></div><p className="text-style-body text-color-muted-foreground">{t("uploadFlow.messages.workflowPage.deployDescription")}</p><label className="block space-y-2 text-style-body-strong">{t("uploadFlow.messages.workflowPage.version")}<select className="block w-full rounded-surface border border-border bg-surface px-3 py-2" value={versionId} onChange={(event) => setVersionId(event.target.value)}><option value="">{t("uploadFlow.messages.workflowPage.chooseImage")}</option>{images.map((version) => <option value={version.id} key={version.id}>{"v" + version.version}{version.aliases?.length ? ` Â· ${version.aliases.join(", ")}` : ""}</option>)}</select></label><label className="block space-y-2 text-style-body-strong">{t("uploadFlow.messages.workflowPage.target")}<select className="block w-full rounded-surface border border-border bg-surface px-3 py-2" value={target} onChange={(event) => setTarget(event.target.value as "staging" | "production")}><option value="staging">{t("uploadFlow.messages.workflowPage.staging")}</option><option value="production">{t("uploadFlow.messages.workflowPage.production")}</option></select></label><Button variant="primary" disabled={busy || !versionId} loading={busy} onClick={() => void deployVersion()}>{t("uploadFlow.messages.workflowPage.deploy")}</Button></section>
      </div>
      <section className="overflow-hidden rounded-surface border border-border bg-surface"><div className="border-b border-border p-4"><h2 className="text-style-section-title">{t("uploadFlow.messages.workflowPage.deployments")}</h2></div>{deployments.length ? <div className="divide-y divide-border">{deployments.map((deployment) => <div className="flex flex-wrap items-center justify-between gap-3 p-4" key={deployment.id}><span>{"v" + (versions.find((item) => item.id === deployment.version_id)?.version ?? deployment.version_id.slice(0, 8)) + " · " + deployment.target}</span><Badge variant={deployment.status === "healthy" ? "success" : ["failed", "unhealthy"].includes(deployment.status) ? "danger" : "neutral"}>{deployment.status}</Badge></div>)}</div> : <p className="p-6 text-style-body text-color-muted-foreground">{t("uploadFlow.messages.workflowPage.noDeployments")}</p>}</section>
    </section>
  );
}
