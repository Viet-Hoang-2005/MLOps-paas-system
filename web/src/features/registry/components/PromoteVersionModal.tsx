import { useState } from "react";
import { Button } from "@/shared/components/Button";
import { toast } from "@/shared/components/toastStore";
import { promoteRegistryVersion } from "@/features/registry/api/registryApi";
import { getApiErrorMessage } from "@/shared/api/errors";
import type {
  RegistryFamily,
  RegistryVersion,
  RoutingAliasName,
} from "@/features/registry/types";
import { AlertCircle, ArrowUpCircle } from "lucide-react";
import { formatVersion } from "@/shared/lib/formatters";
import { useTranslation } from "react-i18next";

interface Props {
  family: RegistryFamily;
  version: RegistryVersion;
  onClose: () => void;
  onSuccess: () => void;
}

export function PromoteVersionModal({
  family,
  version,
  onClose,
  onSuccess,
}: Props) {
  const [loading, setLoading] = useState(false);
  const [alias, setAlias] = useState<RoutingAliasName>("production");
  const { t } = useTranslation("registry");

  const handlePromote = async () => {
    try {
      setLoading(true);
      const result = await promoteRegistryVersion(family.id, version.id, alias);
      toast.success(
        result.message ||
          t("promoteDialog.success", {
            version: formatVersion(version.version),
            alias,
          }),
      );
      if (result.warning) {
        toast.warning(result.warning);
      }
      onSuccess();
    } catch (error) {
      toast.error(
        getApiErrorMessage(
          error,
          t("promoteDialog.failed"),
        ),
      );
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-overlay backdrop-blur-sm p-4">
      <div className="bg-surface rounded-overlay shadow-xl w-full max-w-md overflow-hidden">
        <div className="p-6">
          <div className="flex items-center gap-3 mb-4">
            <div className="rounded-full bg-success-subtle p-2.5 text-color-success">
              <ArrowUpCircle className="h-6 w-6" />
            </div>
            <h3 className="text-style-section-title font-bold text-color-foreground">
              {t("promoteDialog.title")}
            </h3>
          </div>

          <div className="flex gap-3 rounded-surface border border-info-border bg-info-subtle p-4 text-color-info shadow-sm">
            <AlertCircle className="mt-0.5 h-5 w-5 shrink-0 text-color-info" />
            <p className="text-style-body">
              {t("promoteDialog.description")}
            </p>
          </div>

          <div className="mt-6 flex flex-col gap-3 text-style-body bg-muted p-4 rounded-surface border border-border">
            <label className="flex flex-col gap-2 pb-2 border-b border-border">
              <span className="text-color-muted-foreground font-semibold uppercase text-style-caption">
                {t("promoteDialog.alias")}
              </span>
              <select
                value={alias}
                onChange={(event) =>
                  setAlias(event.target.value as RoutingAliasName)
                }
                className="rounded-control border border-border bg-surface px-3 py-2 text-style-body-strong text-color-foreground outline-none focus:border-success focus:ring-2 focus:ring-success-border"
                disabled={loading}
              >
                <option value="production">{t("promoteDialog.production")}</option>
                <option value="latest">{t("promoteDialog.latest")}</option>
                <option value="champion">{t("promoteDialog.champion")}</option>
              </select>
            </label>
            <div className="flex justify-between py-1 border-b border-border">
              <span className="text-color-muted-foreground font-semibold uppercase text-style-caption">
                {t("promoteDialog.targetVersion")}
              </span>
              <span className="rounded-compact bg-success-subtle px-2 font-mono font-bold text-color-success">
                {formatVersion(version.version)}
              </span>
            </div>
            <div className="flex justify-between py-1 border-b border-border">
              <span className="text-color-muted-foreground font-semibold uppercase text-style-caption">
                {t("promoteDialog.currentProduction")}
              </span>
              <span className="font-mono text-color-muted-foreground">
                {family.current_production_version
                  ? formatVersion(family.current_production_version.version)
                  : t("statuses.none", { ns: "common" })}
              </span>
            </div>
            <div className="flex justify-between py-1">
              <span className="text-color-muted-foreground font-semibold uppercase text-style-caption">
                {t("promoteDialog.family")}
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
            onClick={() => void handlePromote()}
            disabled={loading}
            variant="success"
            size="md"
          >
            {loading
              ? t("promoteDialog.submitting")
              : t("promoteDialog.submit", { alias })}
          </Button>
        </div>
      </div>
    </div>
  );
}
