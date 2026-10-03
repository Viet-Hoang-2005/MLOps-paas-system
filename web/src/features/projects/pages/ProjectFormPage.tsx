import { useEffect, useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useBlocker, useNavigate, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  createPreviewProject,
  updatePreview,
} from "@/features/projects/api/previewApi";
import { usePreview } from "@/features/projects/hooks/usePreview";
import { catalogQueryKeys } from "@/features/projects/queryKeys";
import type {
  ModelBuildFormValues,
  BuildInputForm,
  ProjectMetadataForm,
} from "@/features/projects/types";
import { BuildInputFields } from "@/features/projects/components/BuildInputFields";
import { ProjectMetadataFields } from "@/features/projects/components/ProjectMetadataFields";
import { PageHeader } from "@/shared/components/PageHeader";
import { Button } from "@/shared/components/Button";
import { FileDropzone } from "@/shared/components/FileDropzone";
import { ConfirmModal } from "@/shared/components/ConfirmModal";
import { getApiErrorMessage } from "@/shared/api/errors";

const emptyForm: ModelBuildFormValues = {
  name: "",
  description: "",
  access_mode: "private",
  flavor: "sklearn",
  artifact_format: "raw",
  requirements_text: "",
  source_artifact: null,
  source_code_file: null,
  reference_data_file: null,
};

export default function ProjectFormPage() {
  const { modelId } = useParams();
  const { t } = useTranslation("projects");
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const preview = usePreview(modelId);
  const [form, setForm] = useState(emptyForm);
  const [dirty, setDirty] = useState(false);
  const [removed, setRemoved] = useState<string[]>([]);
  const allowExit = useRef(false);
  const initialized = useRef(false);
  useEffect(() => {
    if (!preview.data || initialized.current) return;
    const data = preview.data;
    initialized.current = true;
    setForm((current) => ({
      ...current,
      flavor: data.flavor || "sklearn",
      artifact_format: data.artifact_format,
      requirements_text: data.requirements_text,
    }));
  }, [preview.data]);
  const blocker = useBlocker(() => dirty && !allowExit.current);
  useEffect(() => {
    const handler = (event: BeforeUnloadEvent) => {
      if (dirty && !allowExit.current) event.preventDefault();
    };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [dirty]);
  const setField = <K extends keyof ModelBuildFormValues>(
    key: K,
    value: ModelBuildFormValues[K],
  ) => {
    setForm((current) => ({ ...current, [key]: value }));
    setDirty(true);
  };
  const save = useMutation({
    mutationFn: async () => {
      if (modelId) {
        await updatePreview(modelId, preview.data!.revision, form, removed);
        return modelId;
      }
      return (await createPreviewProject(form)).id;
    },
    onSuccess: async (id) => {
      allowExit.current = true;
      setDirty(false);
      await queryClient.invalidateQueries({
        queryKey: catalogQueryKeys.projects(),
      });
      navigate(`/dashboard/projects/${id}/overview`);
    },
  });
  return (
    <div className="space-y-6">
      <PageHeader
        title={t(modelId ? "workflow.editPreview" : "workflow.newProject")}
      />
      <form
        className="space-y-8 rounded-surface border border-border bg-surface p-6"
        onSubmit={(event) => {
          event.preventDefault();
          save.mutate();
        }}
      >
        {modelId ? (
          <>
            <p>{t("workflow.editHint")}</p>
            <ul className="space-y-2 text-style-caption text-color-muted-foreground">
              {preview.data?.assets.map((asset) => (
                <li key={asset.kind}>
                  <label className="flex items-center gap-2">
                    <input
                      type="checkbox"
                      checked={removed.includes(asset.kind)}
                      onChange={(event) => {
                        setRemoved((current) =>
                          event.target.checked
                            ? [...current, asset.kind]
                            : current.filter((kind) => kind !== asset.kind),
                        );
                        setDirty(true);
                      }}
                    />
                    {t("workflow.removeAsset")}: {asset.kind} · {asset.name}
                  </label>
                </li>
              ))}
            </ul>
            <FileDropzone
              accept=".py"
              subtitle=".py"
              title={form.source_code_file?.name || t("workflow.source")}
              onChange={(file) => setField("source_code_file", file)}
            />
            <FileDropzone
              accept=".csv"
              subtitle=".csv"
              title={form.reference_data_file?.name || t("workflow.reference")}
              onChange={(file) => setField("reference_data_file", file)}
            />
          </>
        ) : (
          <ProjectMetadataFields
            form={form}
            setField={<K extends keyof ProjectMetadataForm>(
              key: K,
              value: ProjectMetadataForm[K],
            ) => {
              setForm((current) => ({ ...current, [key]: value }));
              setDirty(true);
            }}
          />
        )}
        <BuildInputFields
          form={form}
          setField={<K extends keyof BuildInputForm>(
            key: K,
            value: BuildInputForm[K],
          ) => {
            setForm((current) => ({ ...current, [key]: value }));
            setDirty(true);
          }}
        />
        {(save.isError || preview.isError) && (
          <p role="alert" className="text-color-danger">
            {getApiErrorMessage(
              save.error || preview.error,
              t("workflow.failed"),
            )}
          </p>
        )}
        <Button
          type="submit"
          loading={save.isPending}
          disabled={
            modelId ? !preview.data : !form.name.trim() || !form.source_artifact
          }
        >
          {t("workflow.savePreview")}
        </Button>
      </form>
      <ConfirmModal
        open={blocker.state === "blocked"}
        title={t("workflow.unsaved")}
        description={t("workflow.leaveHint")}
        onConfirm={() => blocker.state === "blocked" && blocker.proceed()}
        onCancel={() => blocker.state === "blocked" && blocker.reset()}
      />
    </div>
  );
}
