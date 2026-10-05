import type { VersionEvent } from "@/features/evolution/types";
import { formatDateTime } from "@/shared/i18n/formatters";
import { useTranslation } from "react-i18next";
import { GitCommit, Package } from "lucide-react";

export function VersionHistory({ events }: { events: VersionEvent[] }) {
  const { t, i18n } = useTranslation("evolution");
  if (!events.length)
    return (
      <p className="text-color-muted-foreground">{t("workspace.noEvents")}</p>
    );
  return (
    <ol className="ml-4 space-y-6 border-l border-border py-2">
      {[...events]
        .sort((a, b) => b.created_at.localeCompare(a.created_at))
        .map((event) => (
          <li key={event.id} className="relative pl-8">
            <span
              aria-hidden
              className="absolute -left-4 top-0 flex h-8 w-8 items-center justify-center rounded-full border border-border bg-surface text-color-primary"
            >
              {event.event_type === "registered" ? (
                <Package className="h-4 w-4" />
              ) : (
                <GitCommit className="h-4 w-4" />
              )}
            </span>
            <div className="flex flex-wrap justify-between gap-2">
              <h3 className="text-style-body-strong">
                {event.event_type === "registered"
                  ? t("workspace.registered")
                  : event.event_type === "alias_updated"
                    ? t("workspace.aliasUpdated")
                    : event.event_type}
              </h3>
              <time
                dateTime={event.created_at}
                className="text-style-caption text-color-muted-foreground"
              >
                {formatDateTime(event.created_at, i18n.language)}
              </time>
            </div>
            {(event.from_state || event.to_state) && (
              <p className="mt-2 text-style-caption">
                {t("workspace.transition")}:{" "}
                {event.from_state || t("workspace.missing")} →{" "}
                {event.to_state || t("workspace.missing")}
              </p>
            )}
            {Object.keys(event.metadata).length > 0 && (
              <pre className="mt-3 overflow-auto rounded-surface border border-border bg-muted p-3 text-style-code-sm">
                {JSON.stringify(event.metadata, null, 2)}
              </pre>
            )}
          </li>
        ))}
    </ol>
  );
}
