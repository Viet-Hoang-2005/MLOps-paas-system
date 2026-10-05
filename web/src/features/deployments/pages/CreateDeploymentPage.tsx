import {
  cancelBuildById,
  deployBuild,
  rebuildById,
} from "@/features/deployments/api/deployApi";
import {
  buildPreview,
  buildTraining,
  registerBuild,
} from "@/features/deployments/api/lifecycleApi";
import {
  deploymentFlowKeys,
  useBuild,
  useBuildTrainingSources,
  useDeployment,
} from "@/features/deployments/hooks/useDeploymentFlow";
import { CodeDataFields } from "@/features/projects/components/CodeDataFields";
import { ModelArtifactFields } from "@/features/projects/components/ModelArtifactFields";
import { useModelProjects } from "@/features/projects/hooks/useModelProjects";
import { usePreview } from "@/features/projects/hooks/usePreview";
import type { BuildInputForm, CodeDataForm } from "@/features/projects/types";
import { getApiErrorMessage } from "@/shared/api/errors";
import { Badge } from "@/shared/components/Badge";
import { Button } from "@/shared/components/Button";
import { Callout } from "@/shared/components/Callout";
import { PageHeader } from "@/shared/components/PageHeader";
import { Select, type SelectOption } from "@/shared/components/Select";
import { TerminalViewer } from "@/shared/components/TerminalViewer";
import { useRuntimeLogStream } from "@/shared/hooks/useRuntimeLogStream";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Pause, Play, RotateCcw } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, useSearchParams } from "react-router-dom";

export default function CreateDeploymentPage() {
  const { t } = useTranslation("projects");
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const client = useQueryClient();
  const projects = useModelProjects();
  const buildId = params.get("buildId");
  const build = useBuild(buildId);
  const [selectedModelKey, setSelectedModelKey] = useState<string>("");
  const [selectedProjectId, setSelectedProjectId] = useState<string>("");
  const activeProjectId =
    build.data?.project_id ||
    selectedProjectId ||
    params.get("projectId") ||
    "";
  const activeModelKey =
    selectedModelKey ||
    (build.data?.source_job_id
      ? `training:${build.data.project_id}:${build.data.source_job_id}`
      : activeProjectId
        ? `preview:${activeProjectId}`
        : "");
  const preview = usePreview(activeProjectId);
  const jobs = useBuildTrainingSources();
  const source = activeModelKey.startsWith("training:")
    ? "training"
    : "preview";
  const jobId = source === "training" ? activeModelKey.split(":")[2] : "";

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

  const modelOptions = useMemo<SelectOption[]>(() => {
    const list: SelectOption[] = [];

    (projects.data?.models ?? []).forEach((project) => {
      list.push({
        value: `preview:${project.id}`,
        label: project.name,
        badge: (
          <Badge variant="info" className="ml-auto shrink-0">
            {t("workflow.previewBadge")}
          </Badge>
        ),
      });
    });

    const completedJobs = (jobs.data?.training_jobs ?? []).filter(
      (job) => job.status === "completed" && job.output_available,
    );
    completedJobs.forEach((job) => {
      const project = projects.data?.models.find(
        (p) => p.id === job.project_id,
      );
      const displayName = project ? `${project.name} · ${job.name}` : job.name;
      list.push({
        value: `training:${job.project_id}:${job.id}`,
        label: displayName,
        badge: (
          <Badge variant="success" className="ml-auto shrink-0">
            {t("workflow.trainedBadge")}
          </Badge>
        ),
      });
    });

    return list;
  }, [projects.data?.models, jobs.data?.training_jobs, t]);

  const handleModelChange = (value: string) => {
    setSelectedModelKey(value);
    const next = new URLSearchParams(params);
    next.delete("buildId");
    next.delete("step");
    next.delete("deploymentId");
    if (value.startsWith("preview:")) {
      const pId = value.replace("preview:", "");
      setSelectedProjectId(pId);
      next.set("projectId", pId);
    } else if (value.startsWith("training:")) {
      const [, pId] = value.split(":");
      setSelectedProjectId(pId);
      next.set("projectId", pId);
    }
    setParams(next);
  };

  const selectedJob = useMemo(() => {
    if (source !== "training" || !jobId) return null;
    return (jobs.data?.training_jobs ?? []).find((j) => j.id === jobId) || null;
  }, [source, jobId, jobs.data?.training_jobs]);

  const previewAssets = preview.data?.assets;
  const existingAssets = useMemo(() => {
    if (source === "preview" && previewAssets) {
      const map: Record<string, string> = {};
      previewAssets.forEach((asset) => {
        map[asset.kind] = asset.name;
      });
      return map;
    }
    if (source === "training" && selectedJob) {
      const map: Record<string, string> = {};
      const modelOut = selectedJob.outputs.find((o) => o.kind === "model");
      if (modelOut) map["source_artifact"] = modelOut.relative_path;
      else if (selectedJob.model_artifact_uri)
        map["source_artifact"] = selectedJob.model_artifact_uri;
      if (selectedJob.entry_point || selectedJob.source_zip) {
        map["source_code"] = selectedJob.entry_point || selectedJob.source_zip;
      }
      if (selectedJob.reference_path || selectedJob.training_data) {
        map["reference_data"] =
          selectedJob.reference_path || selectedJob.training_data;
      }
      selectedJob.outputs.forEach((o) => {
        if (o.kind === "metric") map["metrics"] = o.relative_path;
        if (o.kind === "insight") map["model_insights"] = o.relative_path;
      });
      return map;
    }
    return {};
  }, [source, previewAssets, selectedJob]);

  const previewFlavor = preview.data?.flavor;
  const previewFormat = preview.data?.artifact_format;
  const previewReqs = preview.data?.requirements_text;

  const modelForm = useMemo<BuildInputForm>(() => {
    if (source === "training" && selectedJob) {
      return {
        flavor: selectedJob.model_flavor || "sklearn",
        artifact_format: "raw",
        requirements_text: selectedJob.requirements_text || "",
        source_artifact: null,
        source_code_file: null,
        reference_data_file: null,
      };
    }
    return {
      flavor: previewFlavor || "sklearn",
      artifact_format: previewFormat || "raw",
      requirements_text: previewReqs || "",
      source_artifact: null,
      source_code_file: null,
      reference_data_file: null,
    };
  }, [source, selectedJob, previewFlavor, previewFormat, previewReqs]);

  const codeDataForm = useMemo<CodeDataForm>(
    () => ({
      source_code_file: null,
      reference_data_file: null,
    }),
    [],
  );

  const start = useMutation({
    mutationFn: () =>
      buildId
        ? rebuildById(buildId)
        : source === "training"
          ? buildTraining(jobId)
          : buildPreview(activeProjectId, preview.data!.revision),
    onSuccess: (result) =>
      setParams({ projectId: activeProjectId, buildId: result.id }),
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
        projectId: activeProjectId,
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

  const isBuilding =
    start.isPending ||
    Boolean(
      build.data &&
      ["pending", "queued", "building"].includes(build.data.status),
    );

  const isFinished = Boolean(
    build.data && ["ready", "failed", "cancelled"].includes(build.data.status),
  );

  const buildButtonDisabled =
    !activeProjectId ||
    (source === "training"
      ? !jobId
      : !preview.data?.assets?.some(
          (asset) => asset.kind === "source_artifact",
        ));

  const statusBadge = build.data?.status ? (
    <Badge
      variant={
        build.data.status === "ready"
          ? "success"
          : build.data.status === "failed"
            ? "danger"
            : ["pending", "queued", "building"].includes(build.data.status)
              ? "info"
              : "warning"
      }
    >
      {t(`workflow.${build.data.status}`, build.data.status)}
    </Badge>
  ) : undefined;

  const buildActionButton = isBuilding
    ? {
        label: t("workflow.stopBuild"),
        icon: <Pause className="h-4 w-4" />,
        type: "danger" as const,
        loading: cancel.isPending,
        disabled: cancel.isPending,
        onClick: () => cancel.mutate(),
      }
    : isFinished
      ? {
          label: t("workflow.rebuild"),
          icon: <RotateCcw className="h-4 w-4" />,
          type: "primary" as const,
          loading: start.isPending,
          disabled: buildButtonDisabled,
          onClick: () => start.mutate(),
        }
      : {
          label: t("workflow.build"),
          icon: <Play className="h-4 w-4" />,
          type: "primary" as const,
          loading: start.isPending,
          disabled: buildButtonDisabled,
          onClick: () => start.mutate(),
        };

  return (
    <div className="flex min-h-full w-full flex-1 flex-col space-y-6">
      <PageHeader title={t("workflow.createDeployment")} back />

      <section className="flex flex-1 flex-col space-y-6 rounded-surface border border-border bg-surface p-6">
        <Select
          value={activeModelKey}
          onChange={handleModelChange}
          placeholder={t("workflow.selectModels")}
          options={modelOptions}
          disabled={isBuilding}
        />

        {Boolean(activeModelKey && activeProjectId) && (
          <div className="space-y-8 rounded-surface border border-border bg-surface p-6">
            <ModelArtifactFields
              form={modelForm}
              setField={() => {}}
              readOnly
              existingArtifactName={existingAssets.source_artifact}
              existingAssets={existingAssets}
            />
            <hr className="border-border" />
            <CodeDataFields
              form={codeDataForm}
              project={null}
              readOnly
              existingSourceCodeName={existingAssets.source_code}
              existingReferenceDataName={existingAssets.reference_data}
              setField={() => {}}
            />
          </div>
        )}

        <TerminalViewer
          className="flex flex-1 flex-col min-h-72"
          bodyClassName="flex-1 min-h-72 h-full"
          badge={statusBadge}
          logs={logs.logs}
          actionButtons={[buildActionButton]}
        />

        {build.data?.status === "ready" && (
          <Callout
            variant="success"
            title={t("workflow.buildCompleted")}
            description={
              build.data.image_uri
                ? `${t("workflow.readyImageUri")}: ${build.data.image_uri}`
                : t("workflow.buildReadyHint")
            }
          />
        )}

        {build.data?.status === "failed" && (
          <Callout
            variant="danger"
            title={t("workflow.buildFailed")}
            description={
              build.data.error_message ||
              logs.error ||
              t("workflow.buildFailedHint")
            }
          />
        )}

        {build.data?.status === "cancelled" && (
          <Callout
            variant="warning"
            title={t("workflow.buildCancelled")}
            description={build.data.error_message || undefined}
          />
        )}

        {Boolean(build.data?.registration_error) && (
          <Callout
            variant="danger"
            title={t("workflow.registrationFailed")}
            description={build.data?.registration_error}
          />
        )}

        {Boolean(error && build.data?.status !== "failed") && (
          <Callout
            variant="danger"
            title={t("workflow.failed")}
            description={getApiErrorMessage(error, t("workflow.failed"))}
          />
        )}

        {Boolean(logs.error && build.data?.status !== "failed") && (
          <Callout
            variant="danger"
            title={t("workflow.failed")}
            description={logs.error}
          />
        )}

        {deploying && (
          <p className="text-style-caption text-color-foreground-muted">
            {build.data?.version_number} · {build.data?.image_uri}
          </p>
        )}
      </section>

      <div className="grid grid-cols-2 gap-4">
        <Button
          type="button"
          variant="secondary"
          fullWidth
          onClick={() => navigate(-1)}
        >
          {t("workflow.cancel")}
        </Button>

        {deploying || build.data?.version_id ? (
          <Button
            type="button"
            variant="primary"
            fullWidth
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
        ) : (
          <Button
            type="button"
            variant="primary"
            fullWidth
            loading={
              register.isPending ||
              build.data?.registration_status === "registering"
            }
            disabled={
              build.data?.status !== "ready" || Boolean(build.data?.version_id)
            }
            onClick={() => register.mutate()}
          >
            {t("workflow.register")}
          </Button>
        )}
      </div>
      <div className="h-0.5 shrink-0" aria-hidden="true" />
    </div>
  );
}
