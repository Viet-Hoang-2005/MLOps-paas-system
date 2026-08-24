import type { ReactNode } from "react";
import { useModelSelection } from "@/features/catalog/hooks/useModelSelection";
import { useTranslation } from "react-i18next";

export interface PlaceholderProps {
  title: string;
  description: string;
  icon: ReactNode;
  action?: ReactNode;
  showModelName?: boolean;
}

export function Placeholder({
  title,
  description,
  icon,
  action,
  showModelName = true,
}: PlaceholderProps) {
  const { t } = useTranslation("common");
  const { selectedModel } = useModelSelection();

  return (
    <section className="flex-1 rounded-surface border border-dashed border-border bg-surface px-8 py-10">
      <div className="flex h-full flex-col items-center justify-center text-center">
        <div className="mb-5 flex h-12 w-12 items-center justify-center rounded-surface bg-muted text-color-foreground">
          {icon}
        </div>
        {showModelName && (
          <p className="mb-2 text-style-overline uppercase text-color-muted-foreground">
            {selectedModel ? selectedModel.name : t("modelSelector.empty")}
          </p>
        )}
        <h1 className="mb-3 text-style-page-title font-bold text-color-foreground">{title}</h1>
        <p className="max-w-lg text-style-body text-color-muted-foreground">
          {description}
        </p>
        {action && <div className="mt-6">{action}</div>}
      </div>
    </section>
  );
}
