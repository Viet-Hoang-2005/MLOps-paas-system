import { useEffect, useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Hammer, Rocket } from "lucide-react";
import { getProjectVersions, listProjectBuilds } from "@/features/deploy/api/deployApi";
import { rebuildRegistryVersion } from "@/features/registry/api/registryApi";
import { projectPaths } from "@/app/router/paths";
import { PageHeader } from "@/shared/components/PageHeader";
import { Badge } from "@/shared/components/Badge";
import { Button } from "@/shared/components/Button";
import { toast } from "@/shared/components/toastStore";
import { getApiErrorMessage } from "@/shared/api/errors";

export default function RegistryPage() {
  const { projectId = "", versionId } = useParams<{ projectId: string; versionId?: string }>();
  const navigate = useNavigate();
  const { t } = useTranslation("registry");
  const queryClient = useQueryClient();
  const [busy, setBusy] = useState(false);
  const { data: versions = [], isLoading } = useQuery({ queryKey: ["project-versions", projectId], queryFn: () => getProjectVersions(projectId) });
  const { data: builds = [] } = useQuery({ queryKey: ["project-builds", projectId], queryFn: () => listProjectBuilds(projectId) });

  const selected = useMemo(
    () => versions.find((item) => item.id === versionId) ?? versions[0] ?? null,
    [versionId, versions],
  );
  useEffect(() => {
    if (selected && versionId !== selected.id) {
      navigate(projectPaths.evolutionVersion(projectId, selected.id), { replace: true });
    }
  }, [navigate, projectId, selected, versionId]);

  const refreshVersion = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["project-versions", projectId] }),
      queryClient.invalidateQueries({ queryKey: ["project-builds", projectId] }),
    ]);
  };

  const rebuild = async () => {
    if (!selected) return;
    setBusy(true);
    try {
      const data = await rebuildRegistryVersion(selected.id);
      toast.success(t("workflow.rebuildQueued", { id: data.id, version: selected.version }));
      await refreshVersion();
    } catch (error) { toast.error(getApiErrorMessage(error, t("workflow.rebuildFailed"))); }
    finally { setBusy(false); }
  };

  if (isLoading) return <p className="p-8 text-color-muted-foreground">{t("workflow.loading")}</p>;
  return (
    <section className="space-y-6">
      <PageHeader title={t("workflow.title")} description={t("workflow.description")} />
      {versions.length === 0 ? <div className="rounded-surface border border-dashed border-border p-10 text-center"><p>{t("workflow.empty")}</p><Button className="mt-4" variant="primary" onClick={() => navigate(projectPaths.overviewDraft(projectId))}>{t("workflow.openDraft")}</Button></div> : <div className="grid gap-6 lg:grid-cols-[280px_1fr]"><nav className="space-y-2 rounded-surface border border-border bg-surface p-3" aria-label={t("workflow.versions")}>{versions.map((version) => <button key={version.id} className={`w-full rounded-surface border p-3 text-left ${version.id === selected?.id ? "border-primary bg-primary/5" : "border-transparent hover:bg-muted"}`} onClick={() => navigate(projectPaths.evolutionVersion(projectId, version.id))}><span className="flex items-center justify-between"><strong>{t("workflow.version")} {version.version}</strong><span className="text-style-caption">{new Date(version.registered_at).toLocaleDateString()}</span></span><span className="mt-2 flex flex-wrap gap-1">{version.aliases.map((alias) => <Badge key={alias} variant={alias === "production" ? "success" : "primary"}>{alias}</Badge>)}</span></button>)}</nav>{selected && <article className="space-y-5 rounded-surface border border-border bg-surface p-6"><div className="flex flex-wrap items-start justify-between gap-4"><div><h2 className="text-style-section-title">{t("workflow.version")} {selected.version}</h2><p className="mt-1 text-style-caption text-color-muted-foreground">{t("workflow.registered")} {new Date(selected.registered_at).toLocaleString()}</p><div className="mt-3 flex gap-2">{selected.aliases.length ? selected.aliases.map((alias) => <Badge key={alias} variant={alias === "production" ? "success" : "primary"}>{alias}</Badge>) : <Badge variant="neutral">{t("workflow.noAlias")}</Badge>}</div></div><div className="flex gap-2"><Button variant="secondary" disabled={busy} loading={busy} onClick={() => void rebuild()}><Hammer className="mr-2 h-4 w-4" />{t("workflow.rebuild")}</Button><Button variant="primary" onClick={() => navigate(projectPaths.deployment(projectId), { state: { versionId: selected.id } })}><Rocket className="mr-2 h-4 w-4" />{t("workflow.deploy")}</Button></div></div><div className="grid gap-4 sm:grid-cols-3"><div className="rounded-surface bg-muted/30 p-4"><span className="text-style-caption text-color-muted-foreground">{t("workflow.framework")}</span><p>{selected.flavor || t("workflow.unknown")}</p></div><div className="rounded-surface bg-muted/30 p-4"><span className="text-style-caption text-color-muted-foreground">{t("workflow.source")}</span><p>{selected.source_job_id ? t("workflow.trainingJob") : t("workflow.draftOrRebuild")}</p></div><div className="rounded-surface bg-muted/30 p-4"><span className="text-style-caption text-color-muted-foreground">{t("workflow.deployability")}</span><p>{selected.deployability}</p></div></div><div><h3 className="mb-2 font-semibold">{t("workflow.artifacts")}</h3><div className="divide-y divide-border rounded-surface border border-border">{selected.artifacts.map((artifact) => <div key={artifact.id} className="flex flex-wrap justify-between gap-2 p-3"><span><Badge variant="neutral">{artifact.kind}</Badge> {artifact.name}</span><span className="max-w-[50%] truncate font-mono text-style-caption text-color-muted-foreground">{artifact.uri}</span></div>)}</div></div><div><h3 className="mb-2 font-semibold">{t("workflow.buildHistory")}</h3>{builds.filter((build) => build.version_id === selected.id || build.source_version_id === selected.id).map((build) => <div className="flex justify-between border-b border-border py-2" key={build.id}><span>{build.source_kind} · {build.id.slice(0, 8)}</span><Badge variant={build.status === "ready" ? "success" : build.status === "failed" ? "danger" : "neutral"}>{build.status}</Badge></div>)}</div></article>}</div>}
    </section>
  );
}
