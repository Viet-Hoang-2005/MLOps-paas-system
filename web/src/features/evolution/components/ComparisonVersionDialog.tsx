import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import type { ModelVersion } from "@/features/projects/types";
import { comparisonRows } from "@/features/evolution/evolutionState";
import { getVersionDetail } from "@/features/evolution/api/evolutionApi";
import { evolutionQueryKeys } from "@/features/evolution/queryKeys";
import BaseDialog from "@/shared/components/BaseDialog";
import { Button } from "@/shared/components/Button";
import { Select, type SelectOption } from "@/shared/components/Select";
import { getApiErrorMessage } from "@/shared/api/errors";
import { VersionRecords } from "./VersionRecords";

export function ComparisonVersionDialog({
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
  const versionOptions: SelectOption[] = versions.map((version) => ({
    value: version.id,
    label: `v${version.version}`,
  }));
  return (
    <BaseDialog
      title={t("workspace.compare")}
      onClose={onClose}
      description={t("workspace.compareDescription")}
      onCloseAutoFocus={(event) => {
        event.preventDefault();
        restoreFocus();
      }}
      className="w-[min(84vw,62rem)]"
    >
      <div className="space-y-5">
        <div className="grid gap-4 sm:grid-cols-2">
          <Select
            label={t("workspace.left")}
            value={leftId}
            onChange={setLeftId}
            options={versionOptions}
          />
          <Select
            label={t("workspace.right")}
            value={rightId}
            onChange={setRightId}
            options={versionOptions}
          />
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
            ]}
            empty={t("workspace.missing")}
          />
        )}
      </div>
    </BaseDialog>
  );
}
