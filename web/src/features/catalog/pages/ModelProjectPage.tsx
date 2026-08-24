import { Copy, ExternalLink, UploadCloud } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { Placeholder } from "@/shared/components/Placeholder";
import { PageBody } from "@/shared/components/PageBody";
import { Button } from "@/shared/components/Button";
import { useModelSelection } from "@/features/catalog/hooks/useModelSelection";
import { toast } from "@/shared/components/toastStore";
import { useTranslation } from "react-i18next";

export default function ModelProjectPage() {
  const { t, i18n } = useTranslation("catalog");
  const navigate = useNavigate();
  const { selectedModel, loading } = useModelSelection();

  const copyEndpoint = async () => {
    if (!selectedModel?.endpoint_url) return;
    await navigator.clipboard.writeText(selectedModel.endpoint_url);
    toast.success(t("endpointCopied"));
  };

  if (loading)
    return (
      <section className="flex-1 rounded-surface border border-border bg-surface p-8" />
    );

  if (!selectedModel) {
    return (
      <Placeholder
        title={t("noProject")}
        description={t("noProjectDescription")}
        icon={<UploadCloud className="h-6 w-6" />}
        action={
          <Button
            size="md"
            onClick={() => navigate("/dashboard/management/model/upload")}
          >
            {t("upload")}
          </Button>
        }
      />
    );
  }

  return (
    <PageBody>
      <div className="border-b border-border p-6">
        <p className="text-style-caption-strong uppercase text-color-muted-foreground">
          {selectedModel.status}
        </p>
        <h2 className="mt-2 text-style-page-title font-bold text-color-foreground">
          {selectedModel.name}
        </h2>
        <p className="mt-2 max-w-3xl text-style-body text-color-muted-foreground">
          {selectedModel.description || t("noDescription")}
        </p>
      </div>

      <div className="grid gap-4 p-6 lg:grid-cols-3">
        <div className="rounded-surface border border-border bg-muted p-4">
          <p className="text-style-caption-strong uppercase text-color-muted-foreground">
            {t("access")}
          </p>
          <p className="mt-2 text-style-body-strong capitalize text-color-foreground">
            {selectedModel.access_mode}
          </p>
        </div>
        <div className="rounded-surface border border-border bg-muted p-4">
          <p className="text-style-caption-strong uppercase text-color-muted-foreground">
            {t("flavor")}
          </p>
          <p className="mt-2 text-style-body-strong text-color-foreground capitalize">
            {selectedModel.flavor || "-"}
          </p>
        </div>
        <div className="rounded-surface border border-border bg-muted p-4">
          <p className="text-style-caption-strong uppercase text-color-muted-foreground">
            {t("updated")}
          </p>
          <p className="mt-2 text-style-body-strong text-color-foreground">
            {new Date(selectedModel.updated_at).toLocaleString(i18n.language)}
          </p>
        </div>
      </div>

      <div className="border-t border-border p-6">
        <p className="mb-2 text-style-body-strong text-color-foreground">
          {t("endpoint")}
        </p>
        <div className="flex flex-col gap-3 rounded-surface border border-border bg-muted p-3 md:flex-row md:items-center">
          <code className="min-w-0 flex-1 overflow-x-auto text-style-body text-color-foreground">
            {selectedModel.endpoint_url}
          </code>
          <div className="flex gap-2">
            <Button
              variant="secondary"
              size="sm"
              icon={<Copy className="h-4 w-4" />}
              onClick={copyEndpoint}
            >
              {t("copyEndpoint")}
            </Button>
            <Button
              variant="secondary"
              size="sm"
              icon={<ExternalLink className="h-4 w-4" />}
              onClick={() =>
                navigate(`/dashboard/management/model/${selectedModel.id}`)
              }
            >
              {t("manage")}
            </Button>
          </div>
        </div>
      </div>
    </PageBody>
  );
}
