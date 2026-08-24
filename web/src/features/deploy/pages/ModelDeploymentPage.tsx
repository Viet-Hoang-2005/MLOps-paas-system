import type { ModelProject } from "@/features/catalog/types";
import { PackagePreview } from "@/features/deploy/components/PackagePreview";
import { Link } from "react-router-dom";
import { Rocket } from "lucide-react";
import { Button } from "@/shared/components/Button";
import { useTranslation } from "react-i18next";

interface ModelDeploymentPageProps {
  model: ModelProject;
  zipFile: string;
}

export function ModelDeploymentPage({
  model,
  zipFile,
}: ModelDeploymentPageProps) {
  const { t } = useTranslation("deploy");
  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 rounded-surface border border-border bg-muted/40 p-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <p className="font-semibold text-color-foreground">
            {t("deployment.currentMetadataTitle")}
          </p>
          <p className="mt-1 text-style-body text-color-muted-foreground">
            {t("deployment.currentMetadataDescription")}
          </p>
        </div>
        <Link
          to={`/dashboard/management/model/upload/build?modelId=${model.id}`}
        >
          <Button size="md" icon={<Rocket className="h-4 w-4" />}>
            {t("deployment.buildVersion")}
          </Button>
        </Link>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div>
          <p className="text-style-body-strong text-color-muted-foreground">{t("deployment.flavor")}</p>
          <p className="mt-1 text-style-body-lg text-color-foreground capitalize">
            {model.flavor || "-"}
          </p>
        </div>
        <div>
          <p className="text-style-body-strong text-color-muted-foreground">
            {t("deployment.packageFile")}
          </p>
          <p className="mt-1 text-style-body-lg text-color-foreground break-all">{zipFile}</p>
        </div>
        {model.package_preview_tree?.length ? (
          <div className="md:col-span-2">
            <p className="text-style-body-strong text-color-muted-foreground mb-2">
              {t("deployment.packagePreview")}
            </p>
            <PackagePreview preview={model.package_preview_tree} compact />
          </div>
        ) : null}
        <div className="md:col-span-2">
          <p className="text-style-body-strong text-color-muted-foreground">
            {t("deployment.endpoint")}
          </p>
          <code className="mt-2 block bg-muted p-4 rounded-surface text-style-body text-color-foreground font-mono break-all border border-border">
            {model.endpoint_url || "-"}
          </code>
        </div>
      </div>
    </div>
  );
}
