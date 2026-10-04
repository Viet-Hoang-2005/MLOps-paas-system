import {
  createPreviewProject,
  updatePreview,
} from "@/features/projects/api/previewApi";
import { CodeDataFields } from "@/features/projects/components/CodeDataFields";
import { ModelArtifactFields } from "@/features/projects/components/ModelArtifactFields";
import { ModelMetadataFields } from "@/features/projects/components/ModelMetadataFields";
import { usePreview } from "@/features/projects/hooks/usePreview";
import { catalogQueryKeys } from "@/features/projects/queryKeys";
import type { ModelBuildFormValues } from "@/features/projects/types";
import { getApiErrorMessage } from "@/shared/api/errors";
import { Button } from "@/shared/components/Button";
import { ConfirmDialog } from "@/shared/components/ConfirmDialog";
import { PageHeader } from "@/shared/components/PageHeader";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useBlocker, useNavigate, useParams } from "react-router-dom";

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
  const setField = (key: string, value: unknown) => {
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
    <div className="space-y-6 pb-6">
      <PageHeader
        title={t(modelId ? "workflow.editPreview" : "workflow.newProject")}
        back
      />
      <form
        className="space-y-6"
        onSubmit={(event) => {
          event.preventDefault();
          save.mutate();
        }}
      >
        <div className="space-y-8 rounded-surface border border-border bg-surface p-6">
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
              <hr className="border-border" />
            </>
          ) : (
            <>
              <ModelMetadataFields
                form={form}
                setField={(field, value) => setField(field, value)}
              />
              <hr className="border-border" />
            </>
          )}
          <ModelArtifactFields
            form={form}
            setField={(field, value) => setField(field, value)}
          />
          <hr className="border-border" />
          <CodeDataFields
            form={form}
            project={null}
            setField={(field, value) => setField(field, value)}
          />
          {(save.isError || preview.isError) && (
            <p role="alert" className="text-color-danger">
              {getApiErrorMessage(
                save.error || preview.error,
                t("workflow.failed"),
              )}
            </p>
          )}
        </div>

        <div className="grid grid-cols-2 gap-4">
          <Button
            type="button"
            variant="secondary"
            fullWidth
            onClick={() => navigate(-1)}
          >
            {t("workflow.cancel")}
          </Button>
          <Button
            type="submit"
            fullWidth
            loading={save.isPending}
            disabled={
              modelId
                ? !preview.data
                : !form.name.trim() || !form.source_artifact
            }
          >
            {t("workflow.savePreview")}
          </Button>
        </div>
      </form>
      <ConfirmDialog
        open={blocker.state === "blocked"}
        title={t("workflow.unsaved")}
        description={t("workflow.leaveHint")}
        onConfirm={() => blocker.state === "blocked" && blocker.proceed()}
        onCancel={() => blocker.state === "blocked" && blocker.reset()}
      />
    </div>
  );
}
