import { Picker } from "@/shared/components/Picker";
import { useTranslation } from "react-i18next";
import type {
  ModelProject,
  ProjectMetadataForm,
} from "@/features/projects/types";
import { Input } from "@/shared/components/Input";
import { StepTitle } from "@/shared/components/StepTitle";
import { TextArea } from "@/shared/components/TextArea";

interface ModelMetadataFieldsProps {
  form: ProjectMetadataForm;
  project?: ModelProject | null;
  setField: <K extends keyof ProjectMetadataForm>(
    field: K,
    value: ProjectMetadataForm[K],
  ) => void;
}

export function ModelMetadataFields({
  form,
  setField,
}: ModelMetadataFieldsProps) {
  const { t } = useTranslation("deployments");
  return (
    <section className="space-y-5">
      <StepTitle
        title={t("uploadFlow.metadata.title")}
        description={t("uploadFlow.metadata.description")}
      />
      <Input
        id="metadata-name"
        label={t("uploadFlow.metadata.name")}
        value={form.name}
        onChange={(event) => setField("name", event.target.value)}
        placeholder={t("uploadFlow.metadata.namePlaceholder")}
      />
      <TextArea
        id="metadata-description"
        label={t("uploadFlow.metadata.modelDescription")}
        value={form.description}
        onChange={(value) => setField("description", value)}
        placeholder={t("uploadFlow.metadata.descriptionPlaceholder")}
      />
      <Picker
        title={t("uploadFlow.metadata.accessMode")}
        value={form.access_mode}
        onChange={(value) =>
          setField("access_mode", value as ProjectMetadataForm["access_mode"])
        }
        options={[
          {
            value: "private",
            title: t("access.privateTitle"),
            description: t("access.privateDescription"),
          },
          {
            value: "public",
            title: t("access.publicTitle"),
            description: t("access.publicDescription"),
          },
        ]}
      />
    </section>
  );
}
