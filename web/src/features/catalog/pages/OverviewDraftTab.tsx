import { useEffect, useMemo, useState } from "react";
import { Link, useBlocker, useNavigate, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Database, Layers, Rocket, Sparkles, Trash2, UploadCloud } from "lucide-react";
import { useProjectContext } from "@/features/catalog/hooks/useProjectContext";
import { buildDraft, discardDraft, getDraft, loadVersionIntoDraft, patchDraft, removeDraftAsset, saveDraft, uploadDraftAsset, type DraftAssetKind, type ModelDraft } from "@/features/catalog/api/draftApi";
import { projectPaths } from "@/app/router/paths";
import { Badge } from "@/shared/components/Badge";
import { Button } from "@/shared/components/Button";
import { toast } from "@/shared/components/toastStore";
import { getApiErrorMessage } from "@/shared/api/errors";
import { ConfirmModal } from "@/shared/components/ConfirmModal";
import type { ModelFlavor } from "@/features/catalog/types";

const uploadFields: Array<{ kind: DraftAssetKind; titleKey: string; accept: string; required?: boolean }> = [
  { kind: "model", titleKey: "overviewPage.workflow.modelArtifact", accept: ".pkl,.joblib,.json,.ubj,.pt,.pth,.h5,.keras,.onnx,.zip,.tar,.gz", required: true },
  { kind: "reference_data", titleKey: "overviewPage.workflow.referenceData", accept: ".csv,.parquet,.json,.jsonl,.zip,.gz", required: true },
  { kind: "source_code", titleKey: "overviewPage.workflow.sourceZip", accept: ".zip" },
];

export default function OverviewDraftTab() {
  const { projectId = "" } = useParams<{ projectId: string }>();
  const navigate = useNavigate();
  const { t } = useTranslation("catalog");
  const { overview, refetch } = useProjectContext();
  const { draft: overviewDraft, present } = overview;
  const [draft, setDraft] = useState<ModelDraft | null>(null);
  const [loading, setLoading] = useState(true);
  const [working, setWorking] = useState(false);
  const [flavor, setFlavor] = useState<ModelFlavor>((overviewDraft.flavor || "sklearn") as ModelFlavor);
  const [artifactFormat, setArtifactFormat] = useState<"raw" | "archive">((overviewDraft.artifact_format as "raw" | "archive") || "raw");
  const [requirements, setRequirements] = useState(overviewDraft.requirements_snapshot || "");
  const [dirtyMetadata, setDirtyMetadata] = useState(false);
  const locked = draft?.status === "locked" || draft?.status === "saving" || working;

  const refresh = async () => {
    const current = await getDraft(projectId);
    setDraft(current);
    setFlavor((current.flavor || "sklearn") as ModelFlavor);
    setArtifactFormat(current.artifact_format);
    setRequirements(current.requirements_snapshot);
    setDirtyMetadata(false);
    refetch();
  };

  useEffect(() => {
    let active = true;
    getDraft(projectId).then((current) => {
      if (!active) return;
      setDraft(current);
      setFlavor((current.flavor || "sklearn") as ModelFlavor);
      setArtifactFormat(current.artifact_format);
      setRequirements(current.requirements_snapshot);
    }).catch((error) => toast.error(getApiErrorMessage(error, "Could not load Draft."))).finally(() => active && setLoading(false));
    return () => { active = false; };
  }, [projectId]);

  const assets = draft?.assets ?? overviewDraft.assets;
  const canEdit = !locked;
  const dirty = Boolean(draft?.is_dirty || dirtyMetadata);
  const draftPath = projectPaths.overviewDraft(projectId);
  const blocker = useBlocker(({ currentLocation, nextLocation }) =>
    dirty && currentLocation.pathname === draftPath && nextLocation.pathname !== draftPath,
  );
  useEffect(() => {
    if (!dirty) return;
    const handleBeforeUnload = (event: BeforeUnloadEvent) => {
      event.preventDefault();
    };
    window.addEventListener("beforeunload", handleBeforeUnload);
    return () => window.removeEventListener("beforeunload", handleBeforeUnload);
  }, [dirty]);
  const savedLabel = useMemo(() => dirty ? t("overviewPage.workflow.unsaved") : t("overviewPage.workflow.savedRevision", { revision: draft?.saved_revision ?? overviewDraft.saved_revision }), [dirty, draft?.saved_revision, overviewDraft.saved_revision, t]);

  const save = async () => {
    if (!draft) return;
    setWorking(true);
    try {
      let current = draft;
      if (dirtyMetadata) {
        current = await patchDraft(projectId, current.revision, { flavor, artifact_format: artifactFormat, requirements_snapshot: requirements });
      }
      await saveDraft(projectId, current.revision);
      await refresh();
      toast.success(t("overviewPage.workflow.saved"));
    } catch (error) { toast.error(getApiErrorMessage(error, t("overviewPage.workflow.saveFailed"))); }
    finally { setWorking(false); }
  };

  const discard = async () => {
    if (!window.confirm(t("overviewPage.workflow.discardConfirm"))) return;
    setWorking(true);
    try { await discardDraft(projectId); await refresh(); toast.success(t("overviewPage.workflow.discarded")); }
    catch (error) { toast.error(getApiErrorMessage(error, t("overviewPage.workflow.discardFailed"))); }
    finally { setWorking(false); }
  };

  const upload = async (kind: DraftAssetKind, file: File | undefined) => {
    if (!file) return;
    setWorking(true);
    try { await uploadDraftAsset(projectId, kind, file); await refresh(); toast.success(t("overviewPage.workflow.uploaded", { name: file.name })); }
    catch (error) { toast.error(getApiErrorMessage(error, t("overviewPage.workflow.uploadFailed", { name: file.name }))); }
    finally { setWorking(false); }
  };

  const remove = async (kind: DraftAssetKind) => {
    setWorking(true);
    try { await removeDraftAsset(projectId, kind); await refresh(); }
    catch (error) { toast.error(getApiErrorMessage(error, t("overviewPage.workflow.removeFailed"))); }
    finally { setWorking(false); }
  };

  const loadVersion = async (versionId: string) => {
    setWorking(true);
    try {
      await loadVersionIntoDraft(projectId, versionId);
      await refresh();
      toast.success(t("overviewPage.workflow.loaded"));
    } catch (error) { toast.error(getApiErrorMessage(error, t("overviewPage.workflow.loadVersionFailed"))); }
    finally { setWorking(false); }
  };

  const build = async () => {
    setWorking(true);
    try {
      const result = await buildDraft(projectId) as { id?: string };
      toast.success(t("overviewPage.workflow.buildQueued"));
      refetch();
      navigate(projectPaths.deployment(projectId), { state: { buildId: result.id } });
    } catch (error) { toast.error(getApiErrorMessage(error, t("overviewPage.workflow.buildFailed"))); }
    finally { setWorking(false); }
  };

  if (loading) return <div className="p-10 text-center text-color-muted-foreground">{t("overviewPage.workflow.loading")}</div>;

  return (
    <div className="space-y-6">
      <ConfirmModal
        open={blocker.state === "blocked"}
        title={t("overviewPage.workflow.unsaved")}
        description={t("overviewPage.workflow.leaveConfirm")}
        confirmText={t("overviewPage.workflow.leave")}
        tone="danger"
        onConfirm={() => blocker.proceed?.()}
        onCancel={() => blocker.reset?.()}
      />
      <div className="flex border-b border-border">
        <Link to={projectPaths.overviewPresent(projectId)} className="inline-flex h-10 items-center gap-2 px-4 text-style-body-strong text-color-muted-foreground"><Sparkles className="h-4 w-4" />{t("overviewPage.workflow.present")} {present.has_production && <Badge variant={present.is_live ? "success" : "warning"}>{present.is_live ? t("overviewPage.workflow.live") : present.health_status}</Badge>}</Link>
        <Link to={projectPaths.overviewDraft(projectId)} className="inline-flex h-10 items-center gap-2 border-b-2 border-primary px-4 text-style-body-strong text-color-primary"><Layers className="h-4 w-4" />{t("overviewPage.workflow.draft")}</Link>
      </div>
      <section className="space-y-5 rounded-surface border border-border bg-surface p-6">
        <div className="flex flex-wrap items-start justify-between gap-4"><div><h2 className="text-style-section-title">{t("overviewPage.workflow.configuration")}</h2><p className="mt-1 text-style-body text-color-muted-foreground">{t("overviewPage.workflow.immutableNote")}</p><Badge variant={dirty ? "warning" : "success"} className="mt-2">{savedLabel}</Badge></div><div className="flex flex-wrap gap-2"><Button variant="secondary" disabled={!canEdit || !dirty} onClick={() => void discard()}>{t("overviewPage.workflow.discard")}</Button><Button variant="primary" disabled={!canEdit || !dirty} loading={working} onClick={() => void save()}>{t("overviewPage.workflow.save")}</Button></div></div>
        <div className="grid gap-4 md:grid-cols-2">
          <label className="space-y-2 text-style-body-strong">{t("overviewPage.workflow.framework")}<select disabled={!canEdit} className="block w-full rounded-surface border border-border bg-surface px-3 py-2" value={flavor} onChange={(event) => { setFlavor(event.target.value as ModelFlavor); setDirtyMetadata(true); }}><option value="sklearn">Scikit-learn</option><option value="xgboost">XGBoost</option><option value="pytorch">PyTorch</option><option value="tensorflow">{t("overviewPage.workflow.tensorflow")}</option></select></label>
          <label className="space-y-2 text-style-body-strong">{t("overviewPage.workflow.artifactFormat")}<select disabled={!canEdit} className="block w-full rounded-surface border border-border bg-surface px-3 py-2" value={artifactFormat} onChange={(event) => { setArtifactFormat(event.target.value as "raw" | "archive"); setDirtyMetadata(true); }}><option value="raw">{t("overviewPage.workflow.rawArtifact")}</option><option value="archive">{t("overviewPage.workflow.archive")}</option></select></label>
        </div>
        <label className="block space-y-2 text-style-body-strong">{t("overviewPage.workflow.requirements")}<textarea disabled={!canEdit} className="w-full rounded-surface border border-border bg-surface px-3 py-2 font-mono text-style-code-sm" rows={4} value={requirements} onChange={(event) => { setRequirements(event.target.value); setDirtyMetadata(true); }} placeholder={t("overviewPage.workflow.requirementsPlaceholder")} /></label>
        <div className="grid gap-4 md:grid-cols-3">{uploadFields.map((field) => { const asset = assets.find((item) => item.kind === field.kind); return <div key={field.kind} className="space-y-3 rounded-surface border border-border p-4"><div className="flex items-center justify-between gap-2"><strong>{t(field.titleKey)}{field.required ? " *" : ""}</strong>{asset && <Badge variant="success">{t("overviewPage.workflow.attached")}</Badge>}</div>{asset ? <div className="space-y-2 text-style-caption"><a className="block truncate text-color-primary underline" href={asset.download_url} target="_blank" rel="noreferrer">{asset.name}</a><span>{(asset.size_bytes / 1024).toFixed(1)} {t("overviewPage.workflow.sizeKb")}</span>{canEdit && <button className="flex items-center gap-1 text-color-danger" disabled={!canEdit} onClick={() => void remove(field.kind)}><Trash2 className="h-3.5 w-3.5" />{t("overviewPage.workflow.remove")}</button>}</div> : <span className="text-style-caption text-color-muted-foreground">{field.required ? t("overviewPage.workflow.required") : t("overviewPage.workflow.optional")}</span>}<label className="flex cursor-pointer items-center gap-2 rounded-surface border border-dashed border-border p-3 text-style-caption text-color-primary"><UploadCloud className="h-4 w-4" />{asset ? t("overviewPage.workflow.replace") : t("overviewPage.workflow.upload")}<input className="sr-only" type="file" accept={field.accept} disabled={!canEdit} onChange={(event) => { void upload(field.kind, event.target.files?.[0]); event.target.value = ""; }} /></label></div>; })}</div>
        <div className="flex flex-wrap items-center justify-between gap-4 border-t border-border pt-4"><div className="text-style-caption text-color-muted-foreground">{t("overviewPage.workflow.revision")} {draft?.revision}{t("overviewPage.workflow.lastSaved")} {draft?.saved_at ? new Date(draft.saved_at).toLocaleString() : t("overviewPage.workflow.never")}</div><div className="flex gap-2"><label className="flex items-center gap-2 rounded-surface border border-border px-3 py-2 text-style-caption">{t("overviewPage.workflow.loadVersion")}<select className="bg-surface" disabled={!canEdit} defaultValue="" onChange={(event) => { if (event.target.value) void loadVersion(event.target.value); }}><option value="">{t("overviewPage.workflow.choose")}</option>{overview.candidate_versions.map((version) => <option value={version.id} key={version.id}>{"v" + version.version}</option>)}</select></label><Button variant="secondary" disabled={!draft?.can_build || working} onClick={() => void build()}><Rocket className="mr-2 h-4 w-4" />{t("overviewPage.workflow.build")}</Button><Link className="inline-flex items-center gap-2 rounded-surface border border-border px-3 py-2 text-style-caption" to={projectPaths.deployment(projectId)}><Database className="h-4 w-4" />{t("overviewPage.workflow.deployment")}</Link></div></div>
      </section>
    </div>
  );
}

