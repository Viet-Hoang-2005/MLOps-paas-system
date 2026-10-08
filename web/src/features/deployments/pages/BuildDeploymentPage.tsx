import {
  cancelBuildById,
  rebuildById,
} from "@/features/deployments/api/deployApi";
import {
  buildPreview,
  buildTraining,
} from "@/features/deployments/api/lifecycleApi";
import { canRebuild } from "@/features/deployments/buildActions";
import { isRegisteredBuild } from "@/features/deployments/deploymentEligibility";
import { useBuildRegistration } from "@/features/deployments/hooks/useBuildRegistration";
import {
  deploymentFlowKeys,
  useBuild,
  useBuildTrainingSources,
} from "@/features/deployments/hooks/useDeploymentFlow";
import {
  buildDeploymentPath,
  runDeploymentPath,
} from "@/features/deployments/navigation";
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
import { toast } from "@/shared/types/toastStore";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Pause, Play, RotateCcw } from "lucide-react";
import { useEffect, useMemo, useRef } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, useSearchParams } from "react-router-dom";

export default function BuildDeploymentPage() {
  const [params] = useSearchParams();
  return <BuildDeploymentContent key={params.toString()} />;
}

function BuildDeploymentContent() {
  const { t } = useTranslation("projects");
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const client = useQueryClient();
  const projects = useModelProjects();
  const buildId = params.get("buildId");
  const build = useBuild(buildId);
  const activeProjectId =
    build.data?.project_id || params.get("projectId") || "";
  const activeModelKey = build.data?.source_job_id
    ? `training:${build.data.project_id}:${build.data.source_job_id}`
    : params.get("source") === "training" &&
        params.get("jobId") &&
        activeProjectId
      ? `training:${activeProjectId}:${params.get("jobId")}`
      : activeProjectId
        ? `preview:${activeProjectId}`
        : "";
  const preview = usePreview(activeProjectId);
  const jobs = useBuildTrainingSources();
  const projectMismatch = Boolean(
    build.data &&
    params.get("projectId") &&
    params.get("projectId") !== build.data.project_id,
  );
  const source = activeModelKey.startsWith("training:")
    ? "training"
    : "preview";
  const jobId = source === "training" ? activeModelKey.split(":")[2] : "";

  const logs = useRuntimeLogStream({
    source:
      build.data && buildId && !projectMismatch
        ? { kind: "build", id: buildId }
        : null,
    terminalStatuses: ["ready", "failed", "cancelled"],
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
    if (!value) {
      navigate(buildDeploymentPath(), { replace: true });
      return;
    }
    const [kind, projectId, trainingId] = value.split(":");
    navigate(
      buildDeploymentPath({
        projectId,
        source: kind === "training" ? "training" : "preview",
        jobId: trainingId,
      }),
      { replace: true },
    );
  };

  const selectedJob = useMemo(() => {
    if (source !== "training" || !jobId) return null;
    return (
      (jobs.data?.training_jobs ?? []).find(
        (j) => j.id === jobId && j.project_id === activeProjectId,
      ) || null
    );
  }, [source, jobId, activeProjectId, jobs.data?.training_jobs]);

  const previewAssets = preview.data?.assets;
  const existingAssets = useMemo(() => {
    if (build.data) {
      const map: Record<string, string> = {};
      for (const asset of build.data.input_assets) {
        map[asset.kind === "training_output" ? "source_artifact" : asset.kind] =
          asset.name;
      }
      return map;
    }
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
      const sourceCodeOut = selectedJob.outputs.find(
        (o) => o.kind === "source_code",
      );
      if (sourceCodeOut) {
        map["source_code"] = sourceCodeOut.relative_path;
      }
      const refDataOut = selectedJob.outputs.find(
        (o) => o.kind === "reference_data",
      );
      if (refDataOut) {
        map["reference_data"] = refDataOut.relative_path;
      }
      selectedJob.outputs.forEach((o) => {
        if (o.kind === "metric") map["metrics"] = o.relative_path;
        if (o.kind === "insight") map["model_insights"] = o.relative_path;
      });
      return map;
    }
    return {};
  }, [build.data, source, previewAssets, selectedJob]);

  const previewFlavor = preview.data?.flavor;
  const previewFormat = preview.data?.artifact_format;
  const previewReqs = preview.data?.requirements_text;

  const modelForm = useMemo<BuildInputForm>(() => {
    if (build.data) {
      return {
        flavor: build.data.flavor,
        artifact_format:
          build.data.artifact_format === "mlflow_zip" ? "mlflow_zip" : "raw",
        requirements_text: build.data.requirements_snapshot,
        source_artifact: null,
      };
    }
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
  }, [
    build.data,
    source,
    selectedJob,
    previewFlavor,
    previewFormat,
    previewReqs,
  ]);

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
          ? buildTraining(jobId, selectedJob!.output_revision)
          : buildPreview(activeProjectId, preview.data!.revision),
    onSuccess: (result) => {
      client.setQueryData(deploymentFlowKeys.build(result.id), result);
      void client.invalidateQueries({
        queryKey: deploymentFlowKeys.history(result.project_id),
      });
      setParams({ projectId: result.project_id, buildId: result.id });
    },
  });

  const cancel = useMutation({
    mutationFn: () => cancelBuildById(buildId!),
    onSuccess: () =>
      client.invalidateQueries({
        queryKey: deploymentFlowKeys.build(buildId!),
      }),
  });

  const awaitingRegistrationRef = useRef(false);

  const register = useBuildRegistration(buildId, activeProjectId);
  const isRegistering =
    register.isPending || build.data?.registration_status === "registering";

  useEffect(() => {
    if (!awaitingRegistrationRef.current || !build.data) return;

    if (
      isRegisteredBuild(build.data) &&
      build.data.deletion_state === "active"
    ) {
      awaitingRegistrationRef.current = false;
      toast.success(t("workflow.registerSuccess"));
      navigate(runDeploymentPath(build.data.project_id, build.data.id));
    } else if (
      build.data.registration_status === "failed" ||
      Boolean(build.data.registration_error)
    ) {
      awaitingRegistrationRef.current = false;
      toast.error(
        build.data.registration_error || t("workflow.registerFailed"),
      );
    }
  }, [build.data, navigate, t]);

  const handleRegister = () => {
    awaitingRegistrationRef.current = true;
    register.mutate(undefined, {
      onError: (err) => {
        awaitingRegistrationRef.current = false;
        toast.error(getApiErrorMessage(err, t("workflow.registerFailed")));
      },
    });
  };
  const error =
    start.error ||
    cancel.error ||
    build.error ||
    register.error ||
    projects.error ||
    jobs.error ||
    (source === "preview" && !buildId ? preview.error : null);

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
    isRegistering ||
    Boolean(buildId && (!build.data || !canRebuild(build.data))) ||
    !activeProjectId ||
    (source === "training"
      ? !selectedJob?.output_available
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
        disabled:
          cancel.isPending ||
          !buildId ||
          start.isPending ||
          build.data?.deletion_state !== "active",
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

  if (projectMismatch) {
    return (
      <Callout
        variant="danger"
        title={t("workflow.notFound")}
        description={t("workflow.invalidBuildProject")}
      />
    );
  }
  return (
    <div className="flex min-h-full w-full flex-1 flex-col space-y-6">
      <PageHeader title={t("workflow.buildDeployment")} back />

      <section className="flex flex-1 flex-col space-y-6 rounded-surface border border-border bg-surface p-6">
        <Select
          value={activeModelKey}
          onChange={handleModelChange}
          placeholder={t("workflow.selectModels")}
          options={modelOptions}
          disabled={
            isBuilding || isRegistering || Boolean(buildId && !build.data)
          }
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
            description={t("workflow.buildReadyHint")}
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

        {build.data?.registration_status === "registering" && (
          <Callout
            variant="info"
            title={t("workflow.registering")}
            description={t("workflow.registrationInProgress")}
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

        {isRegisteredBuild(build.data) ? (
          <Button
            type="button"
            variant="primary"
            fullWidth
            disabled={build.data?.deletion_state !== "active"}
            onClick={() =>
              navigate(runDeploymentPath(activeProjectId, buildId!))
            }
          >
            {t("workflow.openRunDeployment")}
          </Button>
        ) : (
          <Button
            type="button"
            variant="primary"
            fullWidth
            loading={isRegistering}
            disabled={
              build.data?.status !== "ready" ||
              Boolean(build.data?.version_id) ||
              isRegistering ||
              build.data?.deletion_state !== "active"
            }
            onClick={handleRegister}
          >
            {t("workflow.register")}
          </Button>
        )}
      </div>
      <div className="h-0.5 shrink-0" aria-hidden="true" />
    </div>
  );
}
