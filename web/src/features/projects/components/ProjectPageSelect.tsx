import { useModelSelection } from "@/features/projects/hooks/useModelSelection";
import { Select } from "@/shared/components/Select";
import { useTranslation } from "react-i18next";

export function ProjectPageSelect() {
  const { models, selectedModel, selectModel, loading } = useModelSelection();
  const { t } = useTranslation("common");
  return (
    <div className="w-60 shrink-0">
      <Select
        value={selectedModel?.id ?? ""}
        onChange={selectModel}
        options={models.map((model) => ({ value: model.id, label: model.name }))}
        placeholder={t("modelSelector.empty")}
        aria-label={t("modelSelector.label")}
        disabled={loading || models.length === 0}
        className="h-10"
      />
    </div>
  );
}
