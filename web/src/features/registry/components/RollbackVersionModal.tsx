import { useState } from "react";
import { Button } from "@/shared/components/Button";
import { toast } from "@/shared/components/toastStore";
import { rollbackRegistryFamily } from "@/features/registry/api/registryApi";
import type {
  RegistryFamily,
  RegistryVersion,
} from "@/features/registry/types";
import { AlertCircle, RotateCcw } from "lucide-react";
import { formatVersion } from "@/shared/lib/formatters";
import { useTranslation } from "react-i18next";

interface Props {
  family: RegistryFamily;
  version: RegistryVersion;
  onClose: () => void;
  onSuccess: () => void;
}

export function RollbackVersionModal({
  family,
  version,
  onClose,
  onSuccess,
}: Props) {
  const [loading, setLoading] = useState(false);
  const { t } = useTranslation("registry");

  const handleRollback = async () => {
    try {
      setLoading(true);
      await rollbackRegistryFamily(family.id, version.id);
      toast.success(
        t("rollbackDialog.success", {
          version: formatVersion(version.version),
        }),
      );
      onSuccess();
    } catch {
      toast.error(t("rollbackDialog.failed"));
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-overlay backdrop-blur-sm p-4">
      <div className="bg-surface rounded-overlay shadow-xl w-full max-w-md overflow-hidden">
        <div className="p-6">
          <div className="flex items-center gap-3 mb-4">
            <div className="rounded-full bg-warning-subtle p-2.5 text-color-warning">
              <RotateCcw className="h-6 w-6" />
            </div>
            <h3 className="text-style-section-title font-bold text-color-foreground">
              {t("rollbackDialog.title")}
            </h3>
          </div>

          <div className="flex gap-3 rounded-surface border border-warning-border bg-warning-subtle p-4 text-color-warning shadow-sm">
            <AlertCircle className="mt-0.5 h-5 w-5 shrink-0 text-color-warning" />
            <p className="text-style-body">
              {t("rollbackDialog.description")}
            </p>
          </div>

          <div className="mt-6 flex flex-col gap-3 text-style-body bg-muted p-4 rounded-surface border border-border">
            <div className="flex justify-between py-1 border-b border-border">
              <span className="text-color-muted-foreground font-semibold uppercase text-style-caption">
                {t("rollbackDialog.targetVersion")}
              </span>
              <span className="rounded-compact bg-warning-subtle px-2 font-mono font-bold text-color-warning">
                {formatVersion(version.version)}
              </span>
            </div>
            <div className="flex justify-between py-1 border-b border-border">
              <span className="text-color-muted-foreground font-semibold uppercase text-style-caption">
                {t("rollbackDialog.currentProduction")}
              </span>
              <span className="font-mono text-color-muted-foreground">
                {family.current_production_version
                  ? formatVersion(family.current_production_version.version)
                  : t("statuses.none", { ns: "common" })}
              </span>
            </div>
            <div className="flex justify-between py-1">
              <span className="text-color-muted-foreground font-semibold uppercase text-style-caption">
                {t("rollbackDialog.family")}
              </span>
              <span className="font-bold text-color-foreground">
                {family.display_name || family.name}
              </span>
            </div>
          </div>
        </div>

        <div className="p-4 bg-muted border-t border-border flex justify-end gap-3">
          <Button variant="secondary" onClick={onClose} disabled={loading}>
            {t("actions.cancel", { ns: "common" })}
          </Button>
          <Button
            onClick={() => void handleRollback()}
            disabled={loading}
            variant="warning"
            size="md"
          >
            {loading
              ? t("rollbackDialog.submitting")
              : t("rollbackDialog.submit")}
          </Button>
        </div>
      </div>
    </div>
  );
}
