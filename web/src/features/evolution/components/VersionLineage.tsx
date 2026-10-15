import type { ModelVersion } from "@/features/projects/types";
import { chronologicalVersions } from "@/features/evolution/evolutionState";
import { Badge } from "@/shared/components/Badge";
import { formatDateTime } from "@/shared/i18n/formatters";
import * as Tooltip from "@radix-ui/react-tooltip";
import { useTranslation } from "react-i18next";

export function VersionLineage({
  versions,
  selectedId,
  runningId,
  projectStatus,
  onSelect,
  orientation = "vertical",
}: {
  versions: ModelVersion[];
  selectedId?: string;
  runningId?: string;
  projectStatus?: string;
  onSelect: (id: string) => void;
  orientation?: "vertical" | "horizontal";
}) {
  const { t, i18n } = useTranslation("evolution");
  const isVertical = orientation === "vertical";
  const hasMultipleVersions = (versions.length ?? 0) > 1;
  const hasVersions = (versions.length ?? 0) > 0;

  return (
    <Tooltip.Provider delayDuration={200}>
      <nav
        aria-label={t("workspace.lineage")}
        className={
          isVertical
            ? "relative flex flex-col items-center w-full flex-1 min-h-full"
            : "overflow-x-auto rounded-surface border border-border bg-surface p-5"
        }
      >
        <ol
          className={
            isVertical
              ? `relative flex flex-col items-center gap-5 py-2 w-full flex-1 min-h-full ${
                  hasVersions
                    ? "before:absolute before:top-7 before:bottom-0 before:left-1/2 before:-translate-x-1/2 before:w-0.5 before:bg-border"
                    : ""
                }`
              : `relative flex min-w-max gap-8 ${
                  hasMultipleVersions
                    ? "before:absolute before:left-5 before:right-5 before:top-6 before:h-0.5 before:bg-border"
                    : ""
                }`
          }
        >
        {chronologicalVersions(versions).map((version) => {
          const isRunning = version.id === runningId;
          const isSelected = version.id === selectedId;

          const borderClasses = isSelected
            ? "border-foreground"
            : isRunning
              ? "border-success-border"
              : "border-info-border";

          const bgTextClasses = isRunning
            ? "bg-success-subtle text-color-success"
            : "bg-info-subtle text-color-info";

          const selectedClasses = isSelected
            ? "scale-105 font-bold shadow-sm z-10"
            : "hover:scale-105 transition-transform";

          return (
            <li key={version.id} className="relative">
              <Tooltip.Root>
                <Tooltip.Trigger asChild>
                  <button
                    type="button"
                    aria-current={isSelected ? "true" : undefined}
                    aria-label={`v${version.version} - ${isRunning ? t("workspace.running") : t("workspace.registered")}`}
                    onClick={() => onSelect(version.id)}
                    className={`relative flex h-10 w-10 items-center justify-center rounded-full border-2 text-style-body-strong focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${borderClasses} ${bgTextClasses} ${selectedClasses}`}
                  >
                    <span>{version.version}</span>
                    <span className="sr-only">
                      {`v${version.version}`} {isRunning ? t("workspace.running") : t("workspace.registered")}
                    </span>
                  </button>
                </Tooltip.Trigger>
                <Tooltip.Portal>
                  <Tooltip.Content
                    side={isVertical ? "left" : "bottom"}
                    sideOffset={8}
                    className="z-50 rounded-surface border border-border bg-surface p-3 text-color-foreground shadow-md text-style-caption max-w-xs space-y-1.5"
                  >
                    <div className="flex items-center justify-between gap-3">
                      <p className="font-semibold text-style-body">{`Version v${version.version}`}</p>
                      <Badge variant={isRunning ? "success" : "neutral"}>
                        {isRunning
                          ? t("workspace.running")
                          : projectStatus || t("workspace.registered")}
                      </Badge>
                    </div>
                    <p className="text-color-muted-foreground text-style-caption">
                      {t("workspace.registeredAt")}:{" "}
                      {formatDateTime(version.registered_at, i18n.language)}
                    </p>
                    <Tooltip.Arrow className="fill-border" />
                  </Tooltip.Content>
                </Tooltip.Portal>
              </Tooltip.Root>
            </li>
          );
        })}
      </ol>
    </nav>
  </Tooltip.Provider>
  );
}
