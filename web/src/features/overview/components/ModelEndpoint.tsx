import type { ModelProject } from "@/features/projects/types";
import { Button } from "@/shared/components/Button";
import { Title } from "@/shared/components/Title";
import { toast } from "@/shared/lib/toastStore";
import { Check, Copy } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";

export function ModelEndpoint({ model }: { model: ModelProject }) {
  const { t } = useTranslation("overview");
  const [copied, setCopied] = useState(false);
  const endpointUrl = model.endpoint_url || model.active_endpoint?.url || "";

  const handleCopy = () => {
    if (endpointUrl) {
      void navigator.clipboard.writeText(endpointUrl);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
      toast.success(t("workflow.endpointCopied"));
    }
  };

  return (
    <section className="space-y-4 rounded-surface border border-border bg-surface p-6">
      <Title title={t("workflow.modelEndpoint")} subtitle={t("workflow.modelEndpointHint")} />
      <div className="flex flex-col gap-3 rounded-surface border border-border bg-muted/30 p-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex min-w-0 flex-1 items-center gap-3">
          <span className="shrink-0 text-style-body-strong uppercase text-color-muted-foreground">
            {t("workflow.apiUrl")}
          </span>
          <code className="min-w-0 flex-1 break-all select-all font-mono text-style-body font-medium text-color-foreground">
            {endpointUrl}
          </code>
        </div>
        <Button
          size="sm"
          variant="secondary"
          icon={
            copied ? (
              <Check className="h-4 w-4" />
            ) : (
              <Copy className="h-4 w-4" />
            )
          }
          onClick={handleCopy}
          className="shrink-0"
        >
          {copied ? t("workflow.copied") : t("workflow.copyEndpoint")}
        </Button>
      </div>
    </section>
  );
}
