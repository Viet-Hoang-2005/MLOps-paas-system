import {
  createPreviewProject,
  updatePreview,
} from "@/features/projects/api/previewApi";
import { CodeDataFields } from "@/features/projects/components/CodeDataFields";
import { ModelArtifactFields } from "@/features/projects/components/ModelArtifactFields";
import { ModelMetadataFields } from "@/features/projects/components/ModelMetadataFields";
import { previewKeys, usePreview } from "@/features/projects/hooks/usePreview";
import { catalogQueryKeys } from "@/features/projects/queryKeys";
import type { ModelBuildFormValues } from "@/features/projects/types";
import { getApiErrorMessage } from "@/shared/api/errors";
import { Button } from "@/shared/components/Button";
import { Callout } from "@/shared/components/Callout";
import { ConfirmDialog } from "@/shared/components/ConfirmDialog";
import { PageHeader } from "@/shared/components/PageHeader";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";
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

export default function NewModelProjectPage() {
  const { modelId } = useParams();
  const { t } = useTranslation("projects");
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const preview = usePreview(modelId);
  const [form, setForm] = useState(emptyForm);
  const [dirty, setDirty] = useState(false);
  const [removedAssetKinds, setRemovedAssetKinds] = useState<Set<string>>(
    new Set(),
  );
  const allowExit = useRef(false);
  const initialized = useRef(false);

  const existingArtifact = preview.data?.assets.find(
    (asset) =>
      asset.kind === "source_artifact" &&
      !removedAssetKinds.has("source_artifact"),
  );
  const existingSourceCode = preview.data?.assets.find(
    (asset) =>
      asset.kind === "source_code" && !removedAssetKinds.has("source_code"),
  );
  const existingReferenceData = preview.data?.assets.find(
    (asset) =>
      asset.kind === "reference_data" &&
      !removedAssetKinds.has("reference_data"),
  );

  const filteredExistingAssets = useMemo(() => {
    const map: Record<string, string> = {};
    if (preview.data?.assets) {
      for (const asset of preview.data.assets) {
        if (!removedAssetKinds.has(asset.kind)) {
          map[asset.kind] = asset.name;
        }
      }
    }
    return map;
  }, [preview.data, removedAssetKinds]);

  const hasArtifact = Boolean(form.source_artifact || existingArtifact);

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
    if (value) {
      const assetKind =
        key === "source_artifact"
          ? "source_artifact"
          : key === "source_code_file"
            ? "source_code"
            : key === "reference_data_file"
              ? "reference_data"
              : key.endsWith("_file")
                ? key.replace(/_file$/, "")
                : null;
      if (assetKind) {
        setRemovedAssetKinds((prev) => {
          if (!prev.has(assetKind)) return prev;
          const next = new Set(prev);
          next.delete(assetKind);
          return next;
        });
      }
    }
  };

  const handleRemoveSourceCode = () => {
    setField("source_code_file", null);
    setRemovedAssetKinds((prev) => {
      const next = new Set(prev);
      next.add("source_code");
      return next;
    });
  };

  const handleRemoveReferenceData = () => {
    setField("reference_data_file", null);
    setRemovedAssetKinds((prev) => {
      const next = new Set(prev);
      next.add("reference_data");
      return next;
    });
  };

  const handleRemoveArtifact = () => {
    setField("source_artifact", null);
    setRemovedAssetKinds((prev) => {
      const next = new Set(prev);
      next.add("source_artifact");
      return next;
    });
  };

  const handleRemoveAsset = (kind: string) => {
    const formKey = `${kind}_file` as keyof ModelBuildFormValues;
    if (formKey in form) {
      setField(formKey, null);
    }
    setRemovedAssetKinds((prev) => {
      const next = new Set(prev);
      next.add(kind);
      return next;
    });
  };

  const save = useMutation({
    mutationFn: async () => {
      if (modelId) {
        await updatePreview(
          modelId,
          preview.data!.revision,
          form,
          Array.from(removedAssetKinds),
        );
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
      if (modelId) {
        await queryClient.invalidateQueries({
          queryKey: previewKeys.detail(modelId),
        });
      }
      navigate(`/dashboard/projects/${id}/overview`);
    },
  });
  return (
    <div className="space-y-6">
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
            <Callout variant="info" title={t("workflow.editHint")} />
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
            existingArtifactName={existingArtifact?.name}
            existingAssets={filteredExistingAssets}
            onRemoveArtifact={handleRemoveArtifact}
            onRemoveAsset={handleRemoveAsset}
          />
          <hr className="border-border" />
          <CodeDataFields
            form={form}
            project={null}
            existingSourceCodeName={existingSourceCode?.name}
            existingReferenceDataName={existingReferenceData?.name}
            onRemoveSourceCode={handleRemoveSourceCode}
            onRemoveReferenceData={handleRemoveReferenceData}
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
                ? !preview.data || !hasArtifact
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
      <div className="h-0.5 shrink-0" aria-hidden="true" />
    </div>
  );
}
