import type { ModelProject } from "@/features/projects/types";
import { Select } from "@/shared/components/Select";
import { formatDateTime } from "@/shared/i18n/formatters";
import { useTranslation } from "react-i18next";

export interface InformationOverviewPageProps {
  model: ModelProject;
  onUpdateAccessMode: (accessMode: "private" | "public") => void;
}

export function InformationOverviewPage({
  model,
  onUpdateAccessMode,
}: InformationOverviewPageProps) {
  const { t, i18n } = useTranslation("overview");

  return (
    <section
      role="tabpanel"
      className="space-y-5 rounded-surface border border-border bg-surface p-6"
    >
      <p>{model.name}</p>
      <p>{model.description}</p>
      <p>{model.flavor}</p>
      <p>
        {formatDateTime(model.created_at, i18n.language)} ·{" "}
        {formatDateTime(model.updated_at, i18n.language)}
      </p>
      <Select
        value={model.access_mode}
        onChange={(value) => onUpdateAccessMode(value as "private" | "public")}
        options={[
          { value: "private", label: t("workflow.private") },
          { value: "public", label: t("workflow.public") },
        ]}
      />
    </section>
  );
}

export default InformationOverviewPage;

