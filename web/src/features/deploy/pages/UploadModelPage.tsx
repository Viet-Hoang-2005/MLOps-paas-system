import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { createProjectMetadata } from "@/features/deploy/api/deployApi";
import { getDraft, patchDraft, saveDraft, uploadDraftAsset } from "@/features/catalog/api/draftApi";
import { projectPaths } from "@/app/router/paths";
import { PageHeader } from "@/shared/components/PageHeader";
import { Button } from "@/shared/components/Button";
import { toast } from "@/shared/components/toastStore";
import { getApiErrorMessage } from "@/shared/api/errors";
import type { ModelFlavor } from "@/features/catalog/types";

export default function UploadModelPage() {
  const navigate = useNavigate();
  const { t } = useTranslation("deploy");
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [flavor, setFlavor] = useState<ModelFlavor>("sklearn");
  const [model, setModel] = useState<File | null>(null);
  const [reference, setReference] = useState<File | null>(null);
  const [source, setSource] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    if (!name.trim() || !model || !reference) {
      toast.warning(t("uploadFlow.messages.workflow.required"));
      return;
    }
    setBusy(true);
    let createdProjectId: string | null = null;
    try {
      const project = await createProjectMetadata({
        name: name.trim(), description, access_mode: "private",
      });
      createdProjectId = project.id;
      let draft = await getDraft(project.id);
      draft = await patchDraft(project.id, draft.revision, {
        flavor, artifact_format: "raw", requirements_snapshot: "",
      });
      await uploadDraftAsset(project.id, "model", model);
      await uploadDraftAsset(project.id, "reference_data", reference);
      if (source) await uploadDraftAsset(project.id, "source_code", source);
      draft = await getDraft(project.id);
      await saveDraft(project.id, draft.revision);
      toast.success(t("uploadFlow.messages.workflow.created"));
      navigate(projectPaths.overviewDraft(project.id), { replace: true });
    } catch (error) {
      toast.error(getApiErrorMessage(error, "Could not create the model project Draft."));
      if (createdProjectId) {
        navigate(projectPaths.overviewDraft(createdProjectId), { replace: true });
      }
    } finally {
      setBusy(false);
    }
  };

  const fileField = (labelKey: string, required: boolean, value: File | null, set: (file: File | null) => void, accept: string) => (
    <label className="block space-y-2 text-style-body-strong text-color-foreground">
      <span>{t(labelKey)}{required ? " *" : ` ${t("uploadFlow.messages.workflow.optional")}`}</span>
      <input className="block w-full rounded-surface border border-border bg-surface p-3 text-style-body" type="file" accept={accept} onChange={(event) => set(event.target.files?.[0] ?? null)} />
      {value && <span className="block text-style-caption text-color-muted-foreground">{value.name} · {(value.size / 1024).toFixed(1)} {t("uploadFlow.messages.workflow.sizeKb")}</span>}
    </label>
  );

  return (
    <section className="mx-auto max-w-3xl space-y-6">
      <PageHeader title={t("uploadFlow.messages.workflow.title")} description={t("uploadFlow.messages.workflow.description")} />
      <div className="space-y-5 rounded-surface border border-border bg-surface p-6">
        <label className="block space-y-2 text-style-body-strong">{t("uploadFlow.messages.workflow.projectName")}<input className="w-full rounded-surface border border-border bg-surface px-3 py-2" value={name} maxLength={160} onChange={(event) => setName(event.target.value)} /></label>
        <label className="block space-y-2 text-style-body-strong">{t("uploadFlow.messages.workflow.projectDescription")}<textarea className="w-full rounded-surface border border-border bg-surface px-3 py-2" rows={3} value={description} onChange={(event) => setDescription(event.target.value)} /></label>
        <label className="block space-y-2 text-style-body-strong">{t("uploadFlow.messages.workflow.framework")}<select className="w-full rounded-surface border border-border bg-surface px-3 py-2" value={flavor} onChange={(event) => setFlavor(event.target.value as ModelFlavor)}><option value="sklearn">Scikit-learn</option><option value="xgboost">XGBoost</option><option value="pytorch">PyTorch</option><option value="tensorflow">{t("uploadFlow.messages.workflow.tensorflow")}</option></select></label>
        {fileField("workflow.modelArtifact", true, model, setModel, ".pkl,.joblib,.json,.ubj,.pt,.pth,.h5,.keras,.onnx,.zip,.tar,.gz")}
        {fileField("workflow.referenceData", true, reference, setReference, ".csv,.parquet,.json,.jsonl,.zip,.gz")}
        {fileField("workflow.sourceZip", false, source, setSource, ".zip")}
        <div className="flex justify-end border-t border-border pt-4"><Button variant="primary" loading={busy} disabled={busy} onClick={() => void submit()}>{t("uploadFlow.messages.workflow.saveDraft")}</Button></div>
      </div>
    </section>
  );
}
