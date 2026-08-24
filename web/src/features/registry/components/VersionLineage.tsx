import { Star } from "lucide-react";
import type { RegistryVersion } from "@/features/registry/types";
import { formatVersion } from "@/shared/lib/formatters";
import { useTranslation } from "react-i18next";

interface Props {
  versions: RegistryVersion[];
  selectedVersionId?: string;
  onSelectVersion: (v: RegistryVersion) => void;
}

export function VersionLineage({
  versions,
  selectedVersionId,
  onSelectVersion,
}: Props) {
  const { t } = useTranslation("registry");
  if (versions.length === 0) {
    return (
      <div className="p-8 text-center text-color-muted-foreground text-style-body">
        {t("lineage.empty")}
      </div>
    );
  }

  // Sort oldest to newest for horizontal timeline
  const chronological = [...versions].sort(
    (a, b) =>
      new Date(a.created_at).getTime() - new Date(b.created_at).getTime(),
  );

  return (
    <div className="w-full overflow-x-auto pb-8 custom-scrollbar">
      <div className="relative min-w-full">
        {/* Background horizontal line */}
        <div className="absolute left-0 right-0 top-5 h-0.5 bg-border" />

        <div className="relative flex items-start min-w-max gap-16 px-6">
          {chronological.map((v) => {
            const isProd = v.stage === "production";
            const isSelected = v.id === selectedVersionId;

            return (
              <div
                key={v.id}
                className="relative z-10 flex flex-col items-center bg-background px-2 mt-3"
              >
                <button
                  type="button"
                  onClick={() => onSelectVersion(v)}
                  className={`flex h-4 w-4 items-center justify-center rounded-full border-2 transition-all duration-300 ${
                    isSelected
                      ? "border-primary bg-primary ring-4 ring-primary/20 scale-125"
                      : isProd
                        ? "border-success bg-background hover:bg-success-subtle hover:scale-110"
                        : "border-border bg-background hover:border-primary/50 hover:bg-primary-subtle hover:scale-110"
                  }`}
                >
                  {isProd && (
                    <Star className="h-2 w-2 text-color-success fill-success" />
                  )}
                </button>
                <div className="absolute -bottom-8 flex flex-col items-center gap-1">
                  <span
                    className={`whitespace-nowrap text-style-caption-strong ${
                      isSelected
                        ? "text-color-primary"
                        : isProd
                          ? "text-color-success"
                          : "text-color-foreground"
                    }`}
                  >
                    {formatVersion(v.version)}
                  </span>
                  {isProd && (
                    <span className="text-style-caption uppercase font-bold text-color-success bg-success-subtle px-1.5 rounded-compact">
                      {t("lineage.production")}
                    </span>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
