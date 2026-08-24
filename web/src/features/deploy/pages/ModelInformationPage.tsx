import { Edit3, Save } from "lucide-react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { updateProjectMetadata } from "@/features/deploy/api/deployApi";
import { ProjectMetadataFields } from "@/features/deploy/components/ProjectMetadataFields";
import { getModelProject } from "@/features/catalog/api/catalogApi";
import type {
  ModelProject,
  ProjectMetadataForm,
} from "@/features/catalog/types";
import { getApiErrorMessage } from "@/shared/api/errors";
import { Button } from "@/shared/components/Button";
import { toast } from "@/shared/components/toastStore";

const toForm = (project: ModelProject): ProjectMetadataForm => ({
  name: project.name,
  description: project.description,
  access_mode: project.access_mode,
  source_code_file: null,
  reference_data_file: null,
});

export function ModelInformationPage({ modelId }: { modelId: string }) {
  const { t } = useTranslation("deploy");
  const [project, setProject] = useState<ModelProject | null>(null);
  const [form, setForm] = useState<ProjectMetadataForm | null>(null);
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    getModelProject(modelId)
      .then((result) => {
        setProject(result);
        setForm(toForm(result));
      })
      .catch(() => {
        setProject(null);
        setForm(null);
      });
  }, [modelId]);

  if (!project || !form)
    return (
      <p className="text-style-body text-color-muted-foreground">{t("information.loading")}</p>
    );

  const setField = <K extends keyof ProjectMetadataForm>(
    field: K,
    value: ProjectMetadataForm[K],
  ) => {
    setForm((current) => (current ? { ...current, [field]: value } : current));
  };

  const save = async () => {
    if (!form.name.trim()) {
      toast.warning(t("information.nameRequired"));
      return;
    }
    setSaving(true);
    try {
      const result = await updateProjectMetadata(modelId, form);
      setProject(result);
      setForm(toForm(result));
      setEditing(false);
      toast.success(t("information.saved"));
    } catch (error) {
      toast.error(getApiErrorMessage(error, t("information.saveFailed")));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <p className="text-style-body text-color-muted-foreground">
          {t("information.description")}
        </p>
        {editing ? (
          <div className="flex gap-2">
            <Button
              variant="secondary"
              size="md"
              onClick={() => {
                setForm(toForm(project));
                setEditing(false);
              }}
            >
              {t("actions.cancel", { ns: "common" })}
            </Button>
            <Button
              size="md"
              icon={<Save className="h-4 w-4" />}
              loading={saving}
              onClick={() => void save()}
            >
              {t("actions.save", { ns: "common" })}
            </Button>
          </div>
        ) : (
          <Button
            variant="secondary"
            size="md"
            icon={<Edit3 className="h-4 w-4" />}
            onClick={() => setEditing(true)}
          >
            {t("actions.edit")}
          </Button>
        )}
      </div>
      {editing ? (
        <ProjectMetadataFields
          form={form}
          project={project}
          setField={setField}
        />
      ) : (
        <div className="grid gap-5 md:grid-cols-2">
          <Info label={t("information.modelName")} value={project.name} />
          <Info label={t("information.accessMode")} value={project.access_mode} />
          <Info label={t("information.descriptionLabel")} value={project.description || "-"} />
          <Info label={t("information.sourceCode")} value={project.source_code?.name || "-"} />
          <Info
            label={t("information.referenceData")}
            value={project.reference_data?.name || "-"}
          />
        </div>
      )}
    </div>
  );
}

function Info({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-style-body-strong text-color-muted-foreground">{label}</p>
      <p className="mt-1 whitespace-pre-wrap text-style-body text-color-foreground">
        {value}
      </p>
    </div>
  );
}
