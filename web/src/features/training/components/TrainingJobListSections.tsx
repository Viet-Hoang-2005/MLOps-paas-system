import { useTranslation } from "react-i18next";
import { useMemo } from "react";
import { Select, type SelectOption } from "@/shared/components/Select";

export type TrainingStatusFilter =
  "editing" | "pending" | "success" | "failed" | "all";

export function TrainingJobStatusFilter({
  value,
  onChange,
  className = "w-full sm:w-60",
}: {
  value: TrainingStatusFilter;
  onChange: (value: TrainingStatusFilter) => void;
  className?: string;
}) {
  const { t } = useTranslation("training");
  const options = useMemo<SelectOption[]>(
    () => [
      { value: "all", label: t("statusFilter.all") },
      { value: "editing", label: t("statusFilter.editing") },
      { value: "pending", label: t("statusFilter.pending") },
      { value: "success", label: t("statusFilter.success") },
      { value: "failed", label: t("statusFilter.failed") },
    ],
    [t],
  );

  return (
    <div className={className}>
      <Select
        className="h-10 text-style-body"
        value={value}
        onChange={(val) => onChange(val as TrainingStatusFilter)}
        options={options}
        placeholder={t("statusFilter.placeholder")}
      />
    </div>
  );
}
