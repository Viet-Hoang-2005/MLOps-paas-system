import { Clipboard, X } from "lucide-react";
import { Button } from "@/shared/components/Button";
import { useTranslation } from "react-i18next";

interface ApiModalProps {
  title: string;
  description: string;
  apiKey: string;
  onClose: () => void;
  onCopy: () => void;
}

export function ApiModal({
  title,
  description,
  apiKey,
  onClose,
  onCopy,
}: ApiModalProps) {
  const { t } = useTranslation("settings");
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-overlay px-4">
      <div className="w-full max-w-xl rounded-surface border border-border bg-surface shadow-xl">
        <div className="flex items-center justify-between border-b border-border px-5 py-4">
          <h2 className="text-style-heading font-bold text-color-foreground">{title}</h2>
          <button
            type="button"
            onClick={onClose}
            className="flex h-8 w-8 items-center justify-center rounded-surface text-color-muted-foreground hover:bg-muted hover:text-color-foreground"
            aria-label={t("avatarDialog.close")}
          >
            <X className="h-4 w-4" />
          </button>
        </div>
        <div className="px-5 py-5">
          <div className="rounded-surface border border-warning-border bg-warning-subtle px-4 py-3 text-style-body text-color-warning">
            {description}
          </div>
          <div className="mt-4 rounded-surface border border-border bg-muted p-3">
            <p className="mb-2 text-style-overline uppercase text-color-muted-foreground">
              {t("apiDialog.label")}
            </p>
            <div className="flex items-center gap-2">
              <code className="min-w-0 flex-1 break-all rounded-compact bg-surface px-3 py-2 text-style-body-strong text-color-foreground">
                {apiKey}
              </code>
              <button
                type="button"
                onClick={onCopy}
                className="flex h-10 w-10 shrink-0 items-center justify-center rounded-surface border border-border bg-surface text-color-muted-foreground hover:text-color-foreground"
                aria-label={t("apiDialog.copy")}
              >
                <Clipboard className="h-4 w-4" />
              </button>
            </div>
          </div>
          <div className="mt-6 flex justify-end">
            <Button onClick={onClose}>{t("apiDialog.done")}</Button>
          </div>
        </div>
      </div>
    </div>
  );
}
