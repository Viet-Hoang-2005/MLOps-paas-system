import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useModelProjects } from "@/features/projects/hooks/useModelProjects";
import { usePreview } from "@/features/projects/hooks/usePreview";
import {
  useBuild,
  useDeployment,
  useBuildTrainingSources,
  deploymentFlowKeys,
} from "@/features/deployments/hooks/useDeploymentFlow";
import {
  buildPreview,
  buildTraining,
  registerBuild,
} from "@/features/deployments/api/lifecycleApi";
import {
  cancelBuildById,
  deployBuild,
} from "@/features/deployments/api/deployApi";
import { useRuntimeLogStream } from "@/shared/hooks/useRuntimeLogStream";
import { TerminalViewer } from "@/shared/components/TerminalViewer";
import { PageHeader } from "@/shared/components/PageHeader";
import { Button } from "@/shared/components/Button";
import { Select } from "@/shared/components/Select";
import { getApiErrorMessage } from "@/shared/api/errors";

export default function CreateDeploymentPage() {
  const { t } = useTranslation("projects");
  const [params, setParams] = useSearchParams();
  const client = useQueryClient();
  const projects = useModelProjects();
  const buildId = params.get("buildId");
  const build = useBuild(buildId);
  const projectId = build.data?.project_id || params.get("projectId") || "";
  const preview = usePreview(projectId);
  const jobs = useBuildTrainingSources();
  const [source, setSource] = useState(
    params.get("source") === "training" ? "training" : "preview",
  );
  const [jobId, setJobId] = useState(params.get("jobId") || "");
  const deploying =
    params.get("step") === "deploy" && Boolean(build.data?.version_id);
  const deployment = useDeployment(params.get("deploymentId"));
  const logs = useRuntimeLogStream({
    source:
      deploying && deployment.data
        ? { kind: "deployment", id: deployment.data.id }
        : buildId
          ? { kind: "build", id: buildId }
          : null,
    terminalStatuses: [
      "ready",
      "healthy",
      "failed",
      "cancelled",
      "stopped",
      "unconfirmed",
    ],
  });
  const start = useMutation({
    mutationFn: () =>
      source === "training"
        ? buildTraining(jobId)
        : buildPreview(projectId, preview.data!.revision),
    onSuccess: (result) => setParams({ projectId, buildId: result.id }),
  });
  const register = useMutation({
    mutationFn: () => registerBuild(buildId!),
    onSuccess: async () => {
      await client.invalidateQueries({
        queryKey: deploymentFlowKeys.build(buildId!),
      });
    },
  });
  const cancel = useMutation({
    mutationFn: () => cancelBuildById(buildId!),
    onSuccess: () =>
      client.invalidateQueries({
        queryKey: deploymentFlowKeys.build(buildId!),
      }),
  });
  const registrationHandled = useRef<string | null>(null);
  useEffect(() => {
    if (
      register.isSuccess &&
      build.data?.version_id &&
      registrationHandled.current !== buildId
    ) {
      registrationHandled.current = buildId;
      const next = new URLSearchParams(params);
      next.set("step", "deploy");
      setParams(next);
    }
  }, [register.isSuccess, build.data?.version_id, buildId, params, setParams]);
  const deploy = useMutation({
    mutationFn: () => deployBuild(buildId!),
    onSuccess: (result) =>
      setParams({
        projectId,
        buildId: buildId!,
        step: "deploy",
        deploymentId: result.id,
      }),
  });
  const error =
    start.error ||
    cancel.error ||
    register.error ||
    deploy.error ||
    build.error ||
    deployment.error;
  return (
    <div className="space-y-6">
      <PageHeader title={t("workflow.createDeployment")} back />
      <div className="flex gap-2">
        <Button
          variant={deploying ? "secondary" : "primary"}
          onClick={() => {
            const next = new URLSearchParams(params);
            next.delete("step");
            setParams(next);
          }}
        >
          {t("workflow.stepBuild")}
        </Button>
        <Button
          disabled={!build.data?.version_id}
          variant={deploying ? "primary" : "secondary"}
          onClick={() => {
            const next = new URLSearchParams(params);
            next.set("step", "deploy");
            setParams(next);
          }}
        >
          {t("workflow.stepDeploy")}
        </Button>
      </div>
      <section className="space-y-5 rounded-surface border border-border bg-surface p-6">
        {buildId ? (
          <p>
            {
              projects.data?.models.find((project) => project.id === projectId)
                ?.name
            }{" "}
            · {buildId}
          </p>
        ) : (
          <>
            <Select
              value={projectId}
              onChange={(id) => {
                setParams({ projectId: id });
                setJobId("");
              }}
              placeholder={t("workflow.selectProject")}
              options={(projects.data?.models ?? []).map((project) => ({
                value: project.id,
                label: project.name,
              }))}
            />
            <Select
              value={source}
              onChange={setSource}
              options={[
                { value: "preview", label: t("workflow.preview") },
                { value: "training", label: t("workflow.trained") },
              ]}
            />
            {source === "training" ? (
              <Select
                value={jobId}
                onChange={setJobId}
                placeholder={t("workflow.selectTraining")}
                options={(jobs.data?.training_jobs ?? [])
                  .filter(
                    (job) =>
                      job.project_id === projectId &&
                      job.status === "completed" &&
                      job.output_available,
                  )
                  .map((job) => ({
                    value: job.id,
                    label: `${job.name} · ${job.id}`,
                  }))}
              />
            ) : (
              <ul className="text-style-caption text-color-muted-foreground">
                {preview.data?.assets.map((asset) => (
                  <li key={asset.kind}>
                    {asset.kind}: {asset.name}
                  </li>
                ))}
              </ul>
            )}
          </>
        )}
        <p>
          {deploying
            ? deployment.data?.status || t("workflow.registered")
            : build.data?.status || t("workflow.preview")}
        </p>
        {build.data?.registration_status && (
          <p>{t(`workflow.${build.data.registration_status}`)}</p>
        )}
        <TerminalViewer logs={logs.logs} />
        {logs.error && <p role="alert">{logs.error}</p>}
        {error && (
          <p role="alert" className="text-color-danger">
            {getApiErrorMessage(error, t("workflow.failed"))}
          </p>
        )}
        {build.data?.registration_error && (
          <p role="alert">{build.data.registration_error}</p>
        )}
        {!deploying ? (
          <div className="flex flex-wrap gap-3">
            <Button
              loading={start.isPending}
              disabled={
                Boolean(buildId) ||
                !projectId ||
                (source === "training"
                  ? !jobId
                  : !preview.data?.assets.some(
                      (asset) => asset.kind === "source_artifact",
                    ))
              }
              onClick={() => start.mutate()}
            >
              {t("workflow.build")}
            </Button>
            <Button
              loading={
                register.isPending ||
                build.data?.registration_status === "registering"
              }
              disabled={
                build.data?.status !== "ready" ||
                Boolean(build.data?.version_id)
              }
              onClick={() => register.mutate()}
            >
              {t("workflow.register")}
            </Button>
            {build.data &&
              ["pending", "queued", "building"].includes(build.data.status) && (
                <Button
                  variant="secondary"
                  loading={cancel.isPending}
                  onClick={() => cancel.mutate()}
                >
                  {t("workflow.cancel")}
                </Button>
              )}
            {build.data?.version_id && (
              <Button
                onClick={() => {
                  const next = new URLSearchParams(params);
                  next.set("step", "deploy");
                  setParams(next);
                }}
              >
                {t("workflow.continue")}
              </Button>
            )}
            {build.data &&
              ["ready", "failed", "cancelled"].includes(build.data.status) && (
                <Button
                  variant="secondary"
                  onClick={() => setParams({ projectId })}
                >
                  {t("workflow.newBuild")}
                </Button>
              )}
          </div>
        ) : (
          <>
            <p>
              {build.data?.version_number} · {build.data?.image_uri}
            </p>
            <Button
              loading={deploy.isPending}
              disabled={Boolean(
                deployment.data &&
                ["pending", "deploying", "healthy"].includes(
                  deployment.data.status,
                ),
              )}
              onClick={() => deploy.mutate()}
            >
              {t("workflow.deploy")}
            </Button>
          </>
        )}
      </section>
    </div>
  );
}
