import {
  Activity,
  ExternalLink,
  Layers,
  Sparkles,
  Database,
  ArrowRight,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { Link, useParams } from "react-router-dom";
import { useProjectContext } from "@/features/catalog/hooks/useProjectContext";
import { Badge } from "@/shared/components/Badge";
import { Button } from "@/shared/components/Button";
import { projectPaths } from "@/app/router/paths";

export default function OverviewPresentTab() {
  const { projectId } = useParams<{ projectId: string }>();
  const { t } = useTranslation("catalog");
  const { overview } = useProjectContext();
  const { present } = overview;

  return (
    <div className="space-y-6">
      {/* Sub-tab navigation between Present and Draft */}
      <div className="flex border-b border-border">
        <Link
          to={projectPaths.overviewPresent(projectId!)}
          className="inline-flex h-10 items-center gap-2 border-b-2 border-primary px-4 text-style-body-strong text-color-primary"
        >
          <Sparkles className="h-4 w-4" />
          <span>{t("overviewPage.presentTab", "Present (Production)")}</span>
          {present.has_production ? (
            <Badge variant={present.is_live ? "success" : "warning"} className="ml-1">
              {present.is_live ? t("overviewPage.live", "Live") : present.health_status}
            </Badge>
          ) : (
            <Badge variant="neutral" className="ml-1">
              {t("overviewPage.empty", "Empty")}
            </Badge>
          )}
        </Link>
        <Link
          to={projectPaths.overviewDraft(projectId!)}
          className="inline-flex h-10 items-center gap-2 border-b-2 border-transparent px-4 text-style-body-strong text-color-muted-foreground hover:text-color-foreground"
        >
          <Layers className="h-4 w-4" />
          <span>{t("overviewPage.draftTab", "Draft (Workspace)")}</span>
        </Link>
      </div>

      {present.has_production ? (
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
          {/* Endpoint Status Card */}
          <div className="rounded-surface border border-border bg-surface p-6 shadow-sm lg:col-span-2 space-y-4">
            <div className="flex items-center justify-between">
              <h2 className="text-style-section-title text-color-foreground">
                {t("overviewPage.activeEndpoint", "Active Production Endpoint")}
              </h2>
              <Badge variant={present.is_live ? "success" : "warning"} className="gap-1.5">
                {present.is_live && <span className="h-2 w-2 rounded-full bg-current animate-pulse" />}
                {present.is_live ? t("overviewPage.live", "Live") : present.health_status}
              </Badge>
            </div>

            <div className="space-y-2">
              <span className="text-style-caption text-color-muted-foreground">
                {t("overviewPage.publicUrl", "Public URL")}
              </span>
              <div className="flex items-center gap-2 rounded-surface bg-muted p-3 font-mono text-style-code-sm">
                <span className="truncate flex-1 select-all">
                  {present.endpoint_url || t("overviewPage.notAvailable", "Not available")}
                </span>
                {present.endpoint_url && (
                  <a
                    href={present.endpoint_url}
                    target="_blank"
                    rel="noreferrer"
                    className="text-color-primary hover:text-color-primary"
                  >
                    <ExternalLink className="h-4 w-4" />
                  </a>
                )}
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4 pt-2 sm:grid-cols-3">
              <div>
                <span className="text-style-caption text-color-muted-foreground">
                  {t("overviewPage.modelVersion", "Model Version")}
                </span>
                <p className="font-semibold text-color-foreground">{present.version}</p>
              </div>
              <div>
                <span className="text-style-caption text-color-muted-foreground">
                  {t("overviewPage.harborImage", "Harbor Image")}
                </span>
                <p className="truncate font-mono text-style-code-sm text-color-foreground" title={present.image_uri}>
                  {present.image_uri ? present.image_uri.split("/").pop() : t("overviewPage.none", "None")}
                </p>
              </div>
              <div>
                <span className="text-style-caption text-color-muted-foreground">
                  {t("overviewPage.quickAction", "Quick Action")}
                </span>
                <div>
                  <Link to={projectPaths.playground(projectId!)}>
                    <Button variant="secondary" size="sm" className="mt-0.5">
                      {t("overviewPage.playgroundTest", "Playground Test")}
                    </Button>
                  </Link>
                </div>
              </div>
            </div>
          </div>

          {/* Reference Dataset Baseline Card */}
          <div className="rounded-surface border border-border bg-surface p-6 shadow-sm space-y-4">
            <div className="flex items-center gap-2">
              <Database className="h-5 w-5 text-color-primary" />
              <h2 className="text-style-section-title text-color-foreground">
                {t("overviewPage.baselineSnapshot", "Baseline Snapshot")}
              </h2>
            </div>

            {present.reference_snapshot ? (
              <div className="space-y-3">
                <div>
                  <span className="text-style-caption text-color-muted-foreground">
                    {t("overviewPage.snapshotRole", "Snapshot Role")}
                  </span>
                  <p className="font-medium text-color-foreground">{present.reference_snapshot.role}</p>
                </div>
                <div>
                  <span className="text-style-caption text-color-muted-foreground">
                    {t("overviewPage.rowCount", "Row Count")}
                  </span>
                  <p className="font-medium text-color-foreground">
                    {present.reference_snapshot.row_count} {t("overviewPage.rows", "rows")}
                  </p>
                </div>
                <div>
                  <span className="text-style-caption text-color-muted-foreground">
                    {t("overviewPage.manifestUri", "Manifest URI")}
                  </span>
                  <p className="truncate font-mono text-style-code-sm text-color-muted-foreground" title={present.reference_snapshot.manifest_uri}>
                    {present.reference_snapshot.manifest_uri}
                  </p>
                </div>
                <div className="pt-2">
                  <Link to={`/dashboard/projects/${projectId}/monitoring`}>
                    <Button variant="secondary" size="sm" fullWidth>
                      {t("overviewPage.viewDriftMonitoring", "View Drift Monitoring")}
                    </Button>
                  </Link>
                </div>
              </div>
            ) : (
              <p className="text-style-body text-color-muted-foreground">
                {t("overviewPage.noReferenceSnapshot", "No reference dataset snapshot attached to this version.")}
              </p>
            )}
          </div>

          {/* Metrics Summary */}
          {present.metrics && Object.keys(present.metrics).length > 0 && (
            <div className="rounded-surface border border-border bg-surface p-6 shadow-sm lg:col-span-3 space-y-3">
              <div className="flex items-center gap-2">
                <Activity className="h-5 w-5 text-color-info" />
                <h2 className="text-style-section-title text-color-foreground">
                  {t("overviewPage.performanceMetrics", "Performance Metrics")}
                </h2>
              </div>
              <div className="grid grid-cols-2 gap-4 sm:grid-cols-4 lg:grid-cols-6">
                {Object.entries(present.metrics).map(([key, val]) => (
                  <div key={key} className="rounded-compact border border-border bg-muted/30 p-3">
                    <span className="text-style-caption capitalize text-color-muted-foreground">{key}</span>
                    <p className="text-style-metric font-semibold text-color-foreground">
                      {typeof val === "number" ? val.toFixed(4) : String(val)}
                    </p>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      ) : (
        /* Empty State */
        <div className="flex flex-col items-center justify-center rounded-surface border border-dashed border-border bg-surface/50 p-12 text-center space-y-4">
          <div className="flex h-12 w-12 items-center justify-center rounded-full bg-primary/10 text-color-primary">
            <Sparkles className="h-6 w-6" />
          </div>
          <div className="space-y-1 max-w-md">
            <h3 className="text-style-section-title text-color-foreground">
              {t("overviewPage.noProductionDeployed", "No Production Version Deployed")}
            </h3>
            <p className="text-style-body text-color-muted-foreground">
              {t(
                "overviewPage.noProductionDeployedDesc",
                "This project does not have an active production version yet. Go to the Draft workspace to prepare assets, build an image, and deploy.",
              )}
            </p>
          </div>
          <Link to={projectPaths.overviewDraft(projectId!)}>
            <Button variant="primary">
              {t("overviewPage.switchToDraft", "Switch to Draft Workspace")}
              <ArrowRight className="ml-2 h-4 w-4" />
            </Button>
          </Link>
        </div>
      )}
    </div>
  );
}
