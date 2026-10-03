import { useState } from "react";
import { useTranslation } from "react-i18next";
import type { ModelVersion } from "@/features/projects/types";
import { Select } from "@/shared/components/Select";

export function SnapshotComparison({
  versions,
  selected,
}: {
  versions: ModelVersion[];
  selected: ModelVersion;
}) {
  const { t } = useTranslation("projects");
  const [otherId, setOtherId] = useState("");
  const other = versions.find((version) => version.id === otherId);
  const options = versions
    .filter((version) => version.id !== selected.id)
    .map((version) => ({ value: version.id, label: `v${version.version}` }));
  if (!options.length) return null;
  const fields = (version: ModelVersion) => ({
    flavor: version.flavor,
    requirements: version.requirements_snapshot,
    training_job: version.source_job_id,
    ...Object.fromEntries(
      Object.entries(version.metrics_summary).map(([key, value]) => [
        `metric.${key}`,
        value,
      ]),
    ),
    ...Object.fromEntries(
      Object.entries(version.params_summary).map(([key, value]) => [
        `param.${key}`,
        value,
      ]),
    ),
  });
  const left = fields(selected),
    right = other ? fields(other) : {};
  const keys = [...new Set([...Object.keys(left), ...Object.keys(right)])];
  return (
    <section className="space-y-4">
      <h3 className="text-style-heading">{t("workflow.compareVersions")}</h3>
      <Select
        value={otherId}
        onChange={setOtherId}
        options={options}
        placeholder={t("workflow.selectVersion")}
      />
      {other && (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-style-body">
            <thead>
              <tr>
                <th>{t("workflow.information")}</th>
                <th>{`v${selected.version}`}</th>
                <th>{`v${other.version}`}</th>
              </tr>
            </thead>
            <tbody>
              {keys.map((key) => (
                <tr key={key} className="border-t border-border">
                  <th className="p-2">{key}</th>
                  <td className="max-w-md whitespace-pre-wrap break-all p-2">
                    {JSON.stringify(left[key as keyof typeof left] ?? null)}
                  </td>
                  <td className="max-w-md whitespace-pre-wrap break-all p-2">
                    {JSON.stringify(right[key as keyof typeof right] ?? null)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
