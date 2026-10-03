import { lazy, Suspense, useEffect, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  useBlocker,
  useNavigate,
  useParams,
  useSearchParams,
} from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  useProjectOverview,
  useSnapshotText,
  useRunningSource,
} from "@/features/projects/hooks/useProjectOverview";
import {
  updateModelProject,
  deleteModelProject,
} from "@/features/projects/api/catalogApi";
import { catalogQueryKeys } from "@/features/projects/queryKeys";
import { Button } from "@/shared/components/Button";
import { Input } from "@/shared/components/Input";
import { TextArea } from "@/shared/components/TextArea";
import { Select } from "@/shared/components/Select";
import { ConfirmModal } from "@/shared/components/ConfirmModal";
import { CSVEditor } from "@/shared/components/CSVEditor";
import { getApiErrorMessage } from "@/shared/api/errors";
import { RuntimeMetrics } from "@/features/projects/components/RuntimeMetrics";
import { LazyCodeEditor } from "@/shared/components/LazyCodeEditor";
import { useTheme } from "@/app/theme/useTheme";

const ModelTestingPage = lazy(
  () => import("@/features/projects/pages/ModelTestingPage"),
);

export default function ProjectOverviewPage() {
  const { modelId } = useParams();
  const { t } = useTranslation("projects");
  const { resolvedTheme } = useTheme();
  const navigate = useNavigate();
  const client = useQueryClient();
  const [params, setParams] = useSearchParams();
  const tab = params.get("tab") || "deployment";
  const project = useProjectOverview(modelId);
  const model = project.data;
  const source = useRunningSource(
    tab === "code" ? modelId : undefined,
    model?.active_endpoint?.version_id,
  );
  const reference = useSnapshotText(
    tab === "data" ? model?.reference_data?.download_url : undefined,
    model?.active_endpoint?.version_id,
  );
  const [editing, setEditing] = useState(false);
  const [metadata, setMetadata] = useState({ name: "", description: "" });
  const dirty =
    editing &&
    (metadata.name !== model?.name ||
      metadata.description !== model?.description);
  const blocker = useBlocker(dirty);
  useEffect(() => {
    const onUnload = (event: BeforeUnloadEvent) => {
      if (dirty) event.preventDefault();
    };
    window.addEventListener("beforeunload", onUnload);
    return () => window.removeEventListener("beforeunload", onUnload);
  }, [dirty]);
  const [deleting, setDeleting] = useState(false);
  const update = useMutation({
    mutationFn: async (access?: "private" | "public") =>
      updateModelProject(modelId!, {
        name: editing ? metadata.name : model!.name,
        description: editing ? metadata.description : model!.description,
        access_mode: access || model!.access_mode,
      }),
    onSuccess: async () => {
      setEditing(false);
      await project.refetch();
      await client.invalidateQueries({ queryKey: catalogQueryKeys.projects() });
    },
  });
  const remove = useMutation({
    mutationFn: () => deleteModelProject(modelId!),
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey: catalogQueryKeys.projects() });
      navigate("/dashboard/projects");
    },
  });
  if (project.isError)
    return (
      <p role="alert">
        {getApiErrorMessage(project.error, t("workflow.failed"))}
      </p>
    );
  if (!model) return <p>{t("workflow.loading")}</p>;
  const hasRunning = Boolean(model.active_endpoint);
  return (
    <div className="space-y-6">
      <section className="space-y-4 rounded-surface border border-border bg-surface p-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="space-y-2">
            {editing ? (
              <>
                <Input
                  label={t("workflow.name")}
                  value={metadata.name}
                  onChange={(event) =>
                    setMetadata((current) => ({
                      ...current,
                      name: event.target.value,
                    }))
                  }
                />
                <TextArea
                  label={t("workflow.description")}
                  value={metadata.description}
                  onChange={(description) =>
                    setMetadata((current) => ({ ...current, description }))
                  }
                />
                <Button
                  loading={update.isPending}
                  onClick={() => update.mutate(undefined)}
                >
                  {t("workflow.save")}
                </Button>
                <Button variant="secondary" onClick={() => setEditing(false)}>
                  {t("workflow.cancel")}
                </Button>
              </>
            ) : (
              <>
                <button
                  type="button"
                  className="text-left"
                  onClick={() => {
                    setMetadata({
                      name: model.name,
                      description: model.description,
                    });
                    setEditing(true);
                  }}
                >
                  <h1 className="text-style-page-title">{model.name}</h1>
                  <p className="text-color-muted-foreground">
                    {model.description || t("noDescription")}
                  </p>
                </button>
                <p className="text-style-caption">
                  {t(`workflow.${model.lifecycle_status}`)}
                  {model.preview_changed
                    ? ` · ${t("workflow.previewChanged")}`
                    : ""}
                </p>
              </>
            )}
          </div>
          <div className="flex gap-2">
            <Button
              variant="secondary"
              onClick={() => navigate(`/dashboard/projects/${modelId}/edit`)}
            >
              {t("workflow.editPreview")}
            </Button>
            <Button variant="danger" onClick={() => setDeleting(true)}>
              {t("workflow.delete")}
            </Button>
          </div>
        </div>
        {update.isError && (
          <p role="alert">
            {getApiErrorMessage(update.error, t("workflow.failed"))}
          </p>
        )}
        {model.deletion_state === "delete_failed" && (
          <p role="alert" className="text-color-danger">
            {t("workflow.deletionFailed")} {model.deletion_error}
          </p>
        )}
      </section>
      <div role="tablist" className="flex flex-wrap gap-2">
        {["deployment", "code", "data", "information"].map((key) => (
          <Button
            key={key}
            role="tab"
            aria-selected={tab === key}
            variant={tab === key ? "primary" : "secondary"}
            onClick={() => setParams({ tab: key })}
          >
            {t(`workflow.${key}`)}
          </Button>
        ))}
      </div>
      <section
        role="tabpanel"
        className="space-y-5 rounded-surface border border-border bg-surface p-6"
      >
        {tab === "information" ? (
          <>
            <p>{model.name}</p>
            <p>{model.description}</p>
            <p>{model.flavor}</p>
            <p>
              {new Date(model.created_at).toLocaleString()} ·{" "}
              {new Date(model.updated_at).toLocaleString()}
            </p>
            <Select
              value={model.access_mode}
              onChange={(value) => update.mutate(value as "private" | "public")}
              options={[
                { value: "private", label: t("workflow.private") },
                { value: "public", label: t("workflow.public") },
              ]}
            />
          </>
        ) : !hasRunning ? (
          <>
            <p>{t("workflow.noRunning")}</p>
            <Button
              onClick={() =>
                navigate(`/dashboard/deployments/new?projectId=${modelId}`)
              }
            >
              {t("workflow.deploy")}
            </Button>
          </>
        ) : tab === "deployment" ? (
          <>
            <p>
              {t("workflow.health")}: {model.active_endpoint?.health_status}
            </p>
            <code className="block break-all text-style-code-sm">
              {model.endpoint_url}
            </code>
            <RuntimeMetrics projectId={modelId!} />
            <Suspense fallback={<p>{t("workflow.loading")}</p>}>
              <ModelTestingPage />
            </Suspense>
          </>
        ) : tab === "code" ? (
          source.isError ? (
            <p role="alert">{t("workflow.failed")}</p>
          ) : source.data ? (
            <LazyCodeEditor
              height="400px"
              language="python"
              theme={resolvedTheme === "dark" ? "vs-dark" : "light"}
              value={source.data}
              options={{ readOnly: true, minimap: { enabled: false } }}
            />
          ) : (
            <p>{t("workflow.noSource")}</p>
          )
        ) : reference.isError ? (
          <p role="alert">{t("workflow.failed")}</p>
        ) : reference.data ? (
          <CSVEditor initialCsvText={reference.data} readOnly />
        ) : (
          <p>{t("workflow.noReference")}</p>
        )}
      </section>
      <ConfirmModal
        open={deleting}
        title={t("workflow.delete")}
        description={t("workflow.deleteHint")}
        tone="danger"
        loading={remove.isPending}
        onConfirm={() => remove.mutate()}
        onCancel={() => setDeleting(false)}
      />
      {remove.isError && (
        <p role="alert">
          {getApiErrorMessage(remove.error, t("workflow.failed"))}
        </p>
      )}
      <ConfirmModal
        open={blocker.state === "blocked"}
        title={t("workflow.unsaved")}
        description={t("workflow.leaveHint")}
        onConfirm={() => blocker.proceed?.()}
        onCancel={() => blocker.reset?.()}
      />
    </div>
  );
}
