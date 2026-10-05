import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import type { ModelVersion } from "@/features/projects/types";
import { comparisonRows } from "@/features/evolution/evolutionState";
import { getVersionDetail } from "@/features/evolution/api/evolutionApi";
import { evolutionQueryKeys } from "@/features/evolution/queryKeys";
import BaseDialog from "@/shared/components/BaseDialog";
import { Button } from "@/shared/components/Button";
import { getApiErrorMessage } from "@/shared/api/errors";
import { VersionRecords } from "./VersionRecords";

export function VersionComparisonDialog({
  projectId,
  versions,
  selectedId,
  onClose,
  restoreFocus,
}: {
  projectId: string;
  versions: ModelVersion[];
  selectedId: string;
  onClose: () => void;
  restoreFocus: () => void;
}) {
  const { t } = useTranslation("evolution");
  const [leftId, setLeftId] = useState(selectedId);
  const [rightId, setRightId] = useState(
    versions.find((version) => version.id !== selectedId)?.id ?? "",
  );
  const left = useQuery({
    queryKey: evolutionQueryKeys.snapshot(leftId),
    queryFn: ({ signal }) => getVersionDetail(leftId, signal),
    enabled: versions.some((version) => version.id === leftId),
  });
  const right = useQuery({
    queryKey: evolutionQueryKeys.snapshot(rightId),
    queryFn: ({ signal }) => getVersionDetail(rightId, signal),
    enabled: versions.some((version) => version.id === rightId),
  });
  const valid =
    leftId !== rightId &&
    left.data?.id === leftId &&
    right.data?.id === rightId &&
    left.data?.project_id === projectId &&
    right.data?.project_id === projectId;
  const error = left.error || right.error;
  const rows = valid
    ? comparisonRows(left.data!, right.data!).map((row) => ({
        ...row,
        key:
          row.key === "flavor"
            ? t("workspace.flavor")
            : row.key === "requirements"
              ? t("workspace.requirements")
              : row.key,
      }))
    : [];
  return (
    <BaseDialog
      title={t("workspace.compare")}
      onClose={onClose}
      description={t("workspace.compareDescription")}
      onCloseAutoFocus={(event) => {
        event.preventDefault();
        restoreFocus();
      }}
      className="w-[min(94vw,72rem)]"
    >
      <div className="space-y-5">
        <div className="grid gap-4 sm:grid-cols-2">
          {[
            { id: leftId, set: setLeftId, label: t("workspace.left") },
            { id: rightId, set: setRightId, label: t("workspace.right") },
          ].map((item) => (
            <label
              key={item.label}
              className="space-y-2 text-style-body-strong"
            >
              <span>{item.label}</span>
              <select
                value={item.id}
                onChange={(event) => item.set(event.target.value)}
                className="h-12 w-full rounded-control border border-input bg-surface px-3 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                {versions.map((version) => (
                  <option
                    key={version.id}
                    value={version.id}
                  >{`v${version.version}`}</option>
                ))}
              </select>
            </label>
          ))}
        </div>
        {error ? (
          <div role="alert" className="space-y-3">
            <p>
              {getApiErrorMessage(error, t("workspace.comparisonLoadFailed"))}
            </p>
            <Button
              variant="secondary"
              onClick={() => {
                void left.refetch();
                void right.refetch();
              }}
            >
              {t("workspace.retry")}
            </Button>
          </div>
        ) : left.isLoading || right.isLoading ? (
          <p role="status">{t("workspace.loading")}</p>
        ) : !valid ? (
          <p role="status">{t("workspace.chooseDifferent")}</p>
        ) : (
          <VersionRecords
            key={`${leftId}:${rightId}`}
            rows={rows}
            columns={[
              { key: "key", title: t("workspace.field") },
              { key: "left", title: `v${left.data!.version}` },
              { key: "right", title: `v${right.data!.version}` },
              { key: "delta", title: t("workspace.delta") },
            ]}
            empty={t("workspace.missing")}
          />
        )}
      </div>
    </BaseDialog>
  );
}
