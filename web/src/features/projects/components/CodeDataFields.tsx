import { StepTitle } from "@/shared/components/StepTitle";
import { FileDropzone } from "@/shared/components/FileDropzone";
import { useTranslation } from "react-i18next";
import type { CodeDataForm, ModelProject } from "@/features/projects/types";

interface CodeDataFieldsProps {
  form: CodeDataForm;
  project?: ModelProject | null;
  existingSourceCodeName?: string;
  existingReferenceDataName?: string;
  readOnly?: boolean;
  setField: <K extends keyof CodeDataForm>(
    field: K,
    value: CodeDataForm[K],
  ) => void;
}

export function CodeDataFields({
  form,
  project,
  existingSourceCodeName,
  existingReferenceDataName,
  readOnly = false,
  setField,
}: CodeDataFieldsProps) {
  const { t } = useTranslation("deployments");
  return (
    <section className="space-y-5">
      <StepTitle
        title={t("uploadFlow.metadata.sourcesTitle")}
        description={t("uploadFlow.metadata.sourcesDescription")}
      />
      <FileDropzone
        accept=".zip,.py"
        disabled={readOnly}
        title={
          form.source_code_file?.name ||
          existingSourceCodeName ||
          project?.source_code?.name ||
          t("uploadFlow.metadata.sourceCode")
        }
        subtitle={t("uploadFlow.metadata.sourceHint")}
        onChange={(file) => setField("source_code_file", file)}
      />
      <FileDropzone
        accept=".csv"
        disabled={readOnly}
        title={
          form.reference_data_file?.name ||
          existingReferenceDataName ||
          project?.reference_data?.name ||
          t("uploadFlow.metadata.referenceData")
        }
        subtitle={t("uploadFlow.metadata.referenceHint")}
        onChange={(file) => setField("reference_data_file", file)}
      />
    </section>
  );
}
