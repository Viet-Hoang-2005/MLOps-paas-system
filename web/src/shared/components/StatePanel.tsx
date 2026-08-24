import { AlertCircle, Inbox, RefreshCw } from "lucide-react";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "./Button";

interface StatePanelProps {
  title: string;
  description: string;
  kind?: "empty" | "error";
  icon?: ReactNode;
  action?: ReactNode;
  onRetry?: () => void;
}

export function StatePanel({
  title,
  description,
  kind = "empty",
  icon,
  action,
  onRetry,
}: StatePanelProps) {
  const { t } = useTranslation("common");
  const fallbackIcon =
    kind === "error" ? (
      <AlertCircle className="h-6 w-6" />
    ) : (
      <Inbox className="h-6 w-6" />
    );
  return (
    <section className="flex min-h-64 flex-col items-center justify-center rounded-surface border border-dashed border-border bg-surface px-6 py-12 text-center">
      <div
        className={
          kind === "error"
            ? "mb-4 rounded-surface bg-danger-subtle p-3 text-color-danger"
            : "mb-4 rounded-surface bg-muted p-3 text-color-muted-foreground"
        }
      >
        {icon || fallbackIcon}
      </div>
      <h2 className="text-style-heading text-color-foreground">{title}</h2>
      <p className="mt-2 max-w-md text-style-body text-color-muted-foreground">
        {description}
      </p>
      <div className="mt-5">
        {onRetry ? (
          <Button
            variant="secondary"
            icon={<RefreshCw className="h-4 w-4" />}
            onClick={onRetry}
          >
            {t("actions.retry")}
          </Button>
        ) : (
          action
        )}
      </div>
    </section>
  );
}
