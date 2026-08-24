import {
  ArrowLeft,
  Trash2,
  Download,
  Bot,
  Rocket,
  Database,
  Activity,
} from "lucide-react";
import { Link } from "react-router-dom";
import { useState, useMemo } from "react";
import { useTranslation } from "react-i18next";
import type { ModelProject } from "@/features/catalog/types";
import { Button } from "@/shared/components/Button";
import { useModelProjectMutations } from "@/features/catalog/hooks/useModelProjects";
import { PageTabs } from "@/shared/components/PageTabs";
import { ConfirmModal } from "@/shared/components/ConfirmModal";
import { useParams, useNavigate, useBlocker } from "react-router-dom";
import { useModelProjects } from "@/features/catalog/hooks/useModelProjects";

// Import sub-pages
import { ModelInformationPage } from "./ModelInformationPage";
import { ModelDeploymentPage } from "./ModelDeploymentPage";
import { ModelSourcePage } from "./ModelSourcePage";
import { ModelStatus } from "@/features/deploy/components/ModelStatus";

export default function ModelDetailPage() {
  const { t } = useTranslation("deploy");
  const { modelId } = useParams();
  const { data } = useModelProjects();
  const model = useMemo(
    () => data?.models.find((item) => item.id === modelId) ?? null,
    [data?.models, modelId],
  );

  if (!model) {
    return (
      <div className="p-8 text-center text-color-muted-foreground">
        {t("detail.notFound")}
      </div>
    );
  }

  return <ModelDetailPageContent model={model} />;
}

export function ModelDetailPageContent({ model }: { model: ModelProject }) {
  const { t } = useTranslation("deploy");
  const { tab } = useParams();
  const navigate = useNavigate();

  const activeTab =
    tab === "source"
      ? "3"
      : tab === "deployment"
        ? "2"
        : tab === "status"
          ? "4"
          : "1";

  const handleTabChange = (
    newTab: "information" | "deployment" | "source" | "status",
  ) => {
    navigate(`/dashboard/management/model/${model.id}/${newTab}`);
  };

  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const { deleteModelProject, deleting } = useModelProjectMutations();

  const [sourceCodeDirty, setSourceCodeDirty] = useState(false);
  const [referenceDataDirty, setReferenceDataDirty] = useState(false);
  const isAnyDirty = sourceCodeDirty || referenceDataDirty;

  const blocker = useBlocker(
    ({ currentLocation, nextLocation }) =>
      isAnyDirty && currentLocation.pathname !== nextLocation.pathname,
  );

  const zipFile = useMemo(() => {
    if (!model.model_uri) return "-";
    try {
      const url = new URL(model.model_uri);
      return url.pathname.split("/").pop() || "-";
    } catch {
      return model.model_uri.split("/").pop() || "-";
    }
  }, [model.model_uri]);

  return (
    <>
      <ConfirmModal
        open={blocker.state === "blocked"}
        title={t("detail.discardTitle")}
        description={t("detail.discardDescription")}
        tone="danger"
        confirmText={t("detail.discardConfirm")}
        onConfirm={() => blocker.proceed?.()}
        onCancel={() => blocker.reset?.()}
      />
      <section className="flex flex-col h-full gap-6">
        <div className="flex flex-col gap-4 border-b border-border md:flex-row md:items-end md:justify-between">
          <div className="mb-2">
            <Link
              to="/dashboard/management"
              className="mb-2 inline-flex items-center gap-2 text-style-body-strong text-color-muted-foreground hover:text-color-foreground"
            >
              <ArrowLeft className="h-4 w-4" />
              {t("detail.back")}
            </Link>
            <h1 className="text-style-section-title font-bold text-color-foreground">{t("detail.title")}</h1>
          </div>

          <PageTabs
            tabs={[
              {
                label: t("detail.tabs.information"),
                icon: Bot,
                isActive: activeTab === "1",
                onClick: () => handleTabChange("information"),
              },
              {
                label: t("detail.tabs.deployment"),
                icon: Rocket,
                isActive: activeTab === "2",
                onClick: () => handleTabChange("deployment"),
              },
              {
                label: t("detail.tabs.source"),
                icon: Database,
                isActive: activeTab === "3",
                onClick: () => handleTabChange("source"),
              },
              {
                label: t("detail.tabs.status"),
                icon: Activity,
                isActive: activeTab === "4",
                onClick: () => handleTabChange("status"),
              },
            ]}
          />
        </div>

        <div className="rounded-surface border border-border bg-surface p-6 lg:p-8 flex flex-col flex-1">
          <div className="flex flex-col flex-1">
            {activeTab === "1" && <ModelInformationPage modelId={model.id} />}

            {activeTab === "2" && (
              <ModelDeploymentPage model={model} zipFile={zipFile} />
            )}

            {activeTab === "3" && (
              <ModelSourcePage
                model={model}
                setSourceCodeDirty={setSourceCodeDirty}
                setReferenceDataDirty={setReferenceDataDirty}
              />
            )}

            {activeTab === "4" && <ModelStatus model={model} />}
          </div>

          <div className="mt-12 flex flex-col sm:flex-row items-center gap-4 border-t border-border pt-6 shrink-0">
            <Button
              className="w-full justify-center"
              variant="danger"
              size="md"
              icon={<Trash2 className="h-4 w-4" />}
              loading={deleting}
              onClick={() => setShowDeleteConfirm(true)}
            >
              {t("actions.deleteModel")}
            </Button>
            <Button
              className="w-full justify-center"
              size="md"
              icon={<Download className="h-4 w-4" />}
              onClick={() => {
                if (model.model_uri) {
                  window.open(model.model_uri, "_blank");
                }
              }}
            >
              {t("actions.downloadModel")}
            </Button>
          </div>
        </div>
      </section>

      <ConfirmModal
        open={showDeleteConfirm}
        title={t("detail.deleteTitle")}
        description={t("detail.deleteDescription", { name: model.name })}
        confirmText={t("actions.deleteModel")}
        cancelText={t("actions.cancel", { ns: "common" })}
        tone="danger"
        loading={deleting}
        onConfirm={async () => {
          await deleteModelProject(model.id);
          setShowDeleteConfirm(false);
          // navigate is already handled in useModelProjects hooks onSuccess
        }}
        onCancel={() => setShowDeleteConfirm(false)}
      />
    </>
  );
}
