import type { ModelVersion } from "@/features/projects/types";
import { chronologicalVersions } from "@/features/evolution/evolutionState";
import { Badge } from "@/shared/components/Badge";
import { formatDateTime } from "@/shared/i18n/formatters";
import { GitCommit, Star } from "lucide-react";
import { useTranslation } from "react-i18next";

// Adapted from main's registry VersionLineage; Running is a deployment pointer, not a registry stage.
export function VersionLineage({
  versions,
  selectedId,
  runningId,
  onSelect,
}: {
  versions: ModelVersion[];
  selectedId?: string;
  runningId?: string;
  onSelect: (id: string) => void;
}) {
  const { t, i18n } = useTranslation("evolution");
  return (
    <nav
      aria-label={t("workspace.lineage")}
      className="overflow-x-auto rounded-surface border border-border bg-surface p-5"
    >
      <ol className="relative flex min-w-max gap-8 before:absolute before:inset-x-0 before:top-6 before:h-0.5 before:bg-border">
        {chronologicalVersions(versions).map((version) => (
          <li key={version.id} className="relative min-w-40">
            <button
              type="button"
              aria-current={version.id === selectedId ? "true" : undefined}
              onClick={() => onSelect(version.id)}
              className="relative flex flex-col items-start gap-2 rounded-surface p-1 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <span
                className={`flex h-10 w-10 items-center justify-center rounded-full border-2 ${version.id === selectedId ? "border-primary bg-primary-subtle text-color-primary" : version.id === runningId ? "border-success bg-success-subtle text-color-success" : "border-border bg-surface text-color-muted-foreground"}`}
              >
                {version.id === runningId ? (
                  <Star className="h-4 w-4" />
                ) : (
                  <GitCommit className="h-4 w-4" />
                )}
              </span>
              <span className="text-style-body-strong">{`v${version.version}`}</span>
              <span className="text-style-caption text-color-muted-foreground">
                {formatDateTime(version.registered_at, i18n.language)}
              </span>
              {version.id === runningId && (
                <Badge variant="success">{t("workspace.running")}</Badge>
              )}
            </button>
          </li>
        ))}
      </ol>
    </nav>
  );
}
