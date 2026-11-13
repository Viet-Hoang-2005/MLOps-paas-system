import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  useBlocker,
  useNavigate,
  useParams,
  useSearchParams,
} from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Activity, Clock, Cpu, HardDrive, Pause, Play } from "lucide-react";
import { Button } from "@/shared/components/Button";
import { Badge } from "@/shared/components/Badge";
import { PageHeader } from "@/shared/components/PageHeader";
import { ConfirmDialog } from "@/shared/components/ConfirmDialog";
import { CardSummary } from "@/shared/components/Card";
import { Select, type SelectOption } from "@/shared/components/Select";
import {
  TerminalViewer,
  type TerminalActionItem,
} from "@/shared/components/TerminalViewer";
import { useRuntimeLogStream } from "@/shared/hooks/useRuntimeLogStream";
import { getApiErrorMessage } from "@/shared/api/errors";
import { formatNumber } from "@/shared/i18n/formatters";
import { computeElapsed } from "@/shared/lib/formatDuration";
import { toast } from "@/shared/lib/toastStore";
import { getTrainingStartError } from "@/features/training/api/quotaErrors";
import {
  cancelTrainingJob,
  deleteTrainingOutputs,
  getTrainingJobMetrics,
  getTrainingRuntimeCapabilities,
  getTrainingUsage,
} from "@/features/training/api/trainingApi";
import { formatQuotaDuration } from "@/features/training/api/quotaFormatting";
import {
  getRunInput,
  getTrainingWorkspace,
  getWorkspaceJob,
  isRunResponseError,
  updateTrainingWorkspace,
  runTrainingWorkspace,
} from "@/features/training/api/jobWorkspaceApi";
import {
  WorkspaceEditor,
  type WorkspaceEditorHandle,
} from "@/features/training/components/WorkspaceEditor";
import { TrainingJobDialog } from "@/features/training/components/TrainingJobDialog";
import { VariablesSecretDialog } from "@/features/training/components/VariablesDialog";
import { TrainingProjectAssignment } from "@/features/training/components/TrainingProjectAssignment";
import { trainingQueryKeys } from "@/features/training/queryKeys";
import type {
  TrainingJob,
  TrainingJobFormValues,
} from "@/features/training/types";

const active = (job: TrainingJob) =>
  ["pending", "queued", "running", "uploading", "cancelling"].includes(
    job.status,
  );
const gpuKey = (item: { type: string; device_id?: string; model?: string }) =>
  item.type === "none" ? "none" : item.device_id || item.model || "gpu";

const formatDurationLive = (seconds: number | null | undefined): string => {
  if (seconds == null || seconds < 0) return "-";
  const s = Math.round(seconds);
  if (s === 0) return "0s";
  const hrs = Math.floor(s / 3600);
  const mins = Math.floor((s % 3600) / 60);
  const secs = s % 60;
  if (hrs > 0) return `${hrs}h ${mins}m ${secs}s`;
  if (mins > 0) return `${mins}m ${secs}s`;
  return `${secs}s`;
};

const formatDurationLimit = (seconds: number | null | undefined): string => {
  if (seconds == null || seconds < 0) return "-";
  const s = Math.round(seconds);
  if (s === 0) return "0s";
  const hrs = Math.floor(s / 3600);
  const mins = Math.floor((s % 3600) / 60);
  const secs = s % 60;
  if (hrs > 0) return mins > 0 ? `${hrs}h ${mins}m` : `${hrs}h`;
  if (mins > 0) return secs > 0 ? `${mins}m ${secs}s` : `${mins}m`;
  return `${secs}s`;
};

const formatMegabytes = (
  megabytes: number | null | undefined,
  language: string,
): string => {
  if (megabytes == null) return "-";
  return megabytes >= 1024
    ? `${formatNumber(megabytes / 1024, language, { minimumFractionDigits: 1, maximumFractionDigits: 1 })} GiB`
    : `${formatNumber(Math.round(megabytes), language)} MiB`;
};

export default function TrainingWorkspacePage() {
  const { workspaceId = "", jobId = "" } = useParams();
  return <TrainingTrainingWorkspace key={workspaceId + ":" + jobId} />;
}

function TrainingTrainingWorkspace() {
  const { workspaceId = "", jobId = "" } = useParams();
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { t, i18n } = useTranslation("training");
  const workspaceKey = ["training", "workspace", workspaceId];
  const workspaceQuery = useQuery({
    queryKey: workspaceKey,
    queryFn: () => getTrainingWorkspace(workspaceId),
    refetchInterval: (query) =>
      query.state.data && query.state.data.status !== "ready" ? 3000 : false,
  });
  const capsQuery = useQuery({
    queryKey: ["training", "workspace-capabilities"],
    queryFn: () => getTrainingRuntimeCapabilities(),
  });
  const usageQuery = useQuery({
    queryKey: trainingQueryKeys.usage(),
    queryFn: getTrainingUsage,
    refetchInterval: 15000,
  });
  const usage = usageQuery.data;
  const [busy, setBusy] = useState(false);
  const [editorBusy, setEditorBusy] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [environmentOpen, setEnvironmentOpen] = useState(false);
  const [cpuId, setCpuId] = useState("");
  const [gpu, setGpu] = useState("none");
  const [runtime, setRuntime] = useState<number | null>(null);
  const [flavor, setFlavor] =
    useState<TrainingJobFormValues["model_flavor"]>("sklearn");
  const [saveError, setSaveError] = useState("");
  const [savingConfig, setSavingConfig] = useState(false);
  const [reset, setReset] = useState(0);
  const editor = useRef<WorkspaceEditorHandle>(null);
  const allowNavigation = useRef(false);
  const runKey = useRef<string | null>(null);
  const [historyOpen, setHistoryOpen] = useState(false);
  const saveQueue = useRef<Promise<void>>(Promise.resolve());
  const initialized = useRef("");
  const jobQuery = useQuery({
    queryKey: ["training", "workspace-job", workspaceId, jobId],
    queryFn: () => getWorkspaceJob(workspaceId, jobId),
    enabled: Boolean(jobId),
    refetchInterval: (query) =>
      query.state.data && active(query.state.data) ? 3000 : false,
  });
  const draft = workspaceQuery.data;
  const selectedJob = jobQuery.data;
  useEffect(() => {
    if (params.get("focus") === "terminal" && draft) {
      document
        .getElementById("training-terminal")
        ?.scrollIntoView({ block: "start" });
    }
  }, [params, draft]);
  const workspace = useMemo(
    () =>
      draft && selectedJob
        ? {
            ...draft,
            ...selectedJob,
            id: draft.id,
            revision: selectedJob.input_revision ?? draft.revision,
            environment: selectedJob.environment,
            secrets: selectedJob.secrets,
            status: draft.status,
          }
        : draft,
    [draft, selectedJob],
  );
  const isDraft = !jobId && draft?.status === "ready";
  const selectedRun = jobId;
  const snapshotQuery = useQuery({
    queryKey: ["training", "input", jobId],
    queryFn: () => getRunInput(jobId),
    enabled: Boolean(selectedJob?.submitted_at),
  });
  const hasActiveRun = Boolean(selectedJob && active(selectedJob));
  const locked = busy || editorBusy || hasActiveRun || !isDraft;
  const logStream = useRuntimeLogStream({
    source: selectedJob?.submitted_at ? { kind: "training", id: jobId } : null,
    enabled: Boolean(selectedJob?.submitted_at),
    terminalStatuses: ["completed", "failed", "cancelled"],
  });
  const refresh = useCallback(async () => {
    const data = await getTrainingWorkspace(workspaceId);
    queryClient.setQueryData(["training", "workspace", workspaceId], data);
    return data;
  }, [queryClient, workspaceId]);
  const metricsQuery = useQuery({
    queryKey: trainingQueryKeys.metrics(jobId),
    queryFn: () => getTrainingJobMetrics(jobId),
    enabled: Boolean(jobId) && hasActiveRun,
    refetchInterval: hasActiveRun
      ? selectedJob?.backend === "docker"
        ? 5000
        : 10000
      : false,
  });
  const latestMetric = hasActiveRun
    ? (metricsQuery.data?.latest ?? null)
    : null;

  const [liveElapsed, setLiveElapsed] = useState<number | null>(null);
  const startedAt = hasActiveRun
    ? selectedJob?.started_at ||
      selectedJob?.runtime_started_at ||
      selectedJob?.submitted_at
    : null;
  const initialElapsed = startedAt ? computeElapsed(startedAt) : null;
  const currentElapsed =
    liveElapsed ??
    (initialElapsed != null ? Math.max(0, Math.round(initialElapsed)) : null);

  useEffect(() => {
    if (!hasActiveRun || !startedAt) return;
    const intervalId = window.setInterval(() => {
      const elapsed = computeElapsed(startedAt);
      setLiveElapsed(elapsed != null ? Math.max(0, Math.round(elapsed)) : 0);
    }, 1000);
    return () => {
      window.clearInterval(intervalId);
      setLiveElapsed(null);
    };
  }, [hasActiveRun, startedAt]);
  const caps = capsQuery.data;
  useEffect(() => {
    if (!workspace || !caps || initialized.current === workspaceId) return;
    initialized.current = workspaceId;
    const chosen = caps.cpu_profiles.find(
      (item) =>
        item.vcpu === workspace.vcpu && item.memory_mb === workspace.memory_mb,
    );
    setCpuId(
      chosen?.id ??
        (workspace.vcpu
          ? "unavailable"
          : ((
              caps.cpu_profiles.find((item) => item.id === "medium") ??
              caps.cpu_profiles[0]
            )?.id ?? "")),
    );
    setGpu(
      workspace.accelerator_type === "gpu"
        ? workspace.local_gpu_id || workspace.accelerator_model
        : "none",
    );
    setRuntime(
      workspace.max_runtime_seconds ??
        caps.runtime_options_seconds?.at(-1) ??
        86400,
    );
    setFlavor(workspace.model_flavor);
  }, [workspace, caps, workspaceId]);
  const cpu = caps?.cpu_profiles.find((item) => item.id === cpuId);
  const accelerators = useMemo(
    () => caps?.accelerators ?? [],
    [caps?.accelerators],
  );
  const accelerator = accelerators.find((item) => gpuKey(item) === gpu);
  const maxRuntime = runtime ?? caps?.runtime_options_seconds?.at(-1) ?? 86400;
  const settingsValue = useMemo(
    () =>
      cpu && accelerator
        ? {
            model_flavor: flavor,
            vcpu: cpu.vcpu,
            memory_mb: cpu.memory_mb,
            max_runtime_seconds: maxRuntime,
            accelerator_type: accelerator.type,
            accelerator_count: accelerator.type === "gpu" ? 1 : 0,
            accelerator_model: accelerator.model ?? "",
            local_gpu_id: accelerator.device_id ?? "",
          }
        : null,
    [cpu, accelerator, flavor, maxRuntime],
  );
  const configDirty = Boolean(
    isDraft &&
    settingsValue &&
    workspace &&
    !Object.entries(settingsValue).every(
      ([key, value]) => workspace[key as keyof typeof workspace] === value,
    ),
  );
  const blocker = useBlocker(
    ({ currentLocation, nextLocation }) =>
      (dirty || configDirty) &&
      !allowNavigation.current &&
      `${currentLocation.pathname}${currentLocation.search}` !==
        `${nextLocation.pathname}${nextLocation.search}`,
  );
  useEffect(() => {
    if (!dirty && !configDirty) return;
    const warn = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty, configDirty]);
  const persistSettings = useCallback(async () => {
    if (!settingsValue) return;
    const revision = await editor.current?.saveAll();
    const current = await refresh();
    if (current.status !== "ready") return;
    if (
      Object.entries(settingsValue).every(
        ([key, value]) => current[key as keyof typeof current] === value,
      )
    )
      return;
    await updateTrainingWorkspace(
      workspaceId,
      revision ?? current.revision,
      settingsValue,
    );
    await refresh();
  }, [settingsValue, workspaceId, refresh]);
  useEffect(() => {
    if (!isDraft || !settingsValue || initialized.current !== workspaceId)
      return;
    const timer = setTimeout(() => {
      setSavingConfig(true);
      saveQueue.current = saveQueue.current
        .catch(() => {})
        .then(persistSettings)
        .then(() => setSaveError(""))
        .catch((error: unknown) => {
          setSaveError(getApiErrorMessage(error, t("studio.failed")));
        })
        .finally(() => setSavingConfig(false));
    }, 400);
    return () => clearTimeout(timer);
  }, [isDraft, settingsValue, persistSettings, workspaceId, t]);
  async function start() {
    if (!workspace || !cpu || !accelerator || !isDraft) return;
    setBusy(true);
    try {
      await saveQueue.current;
      await persistSettings();
      const revision = await editor.current!.saveAll();
      runKey.current ??= crypto.randomUUID();
      const job = await runTrainingWorkspace(
        workspaceId,
        revision,
        runKey.current,
      );
      setDirty(false);
      setSaveError("");
      allowNavigation.current = true;
      navigate(
        "/dashboard/training/workspaces/" + workspaceId + "/jobs/" + job.id,
      );
      await refresh();
      void queryClient.invalidateQueries({
        queryKey: trainingQueryKeys.jobs(),
      });
      void queryClient.invalidateQueries({
        queryKey: trainingQueryKeys.usage(),
      });
    } catch (error) {
      if (isRunResponseError(error)) runKey.current = null;
      void refresh();
      toast.error(getTrainingStartError(error, t, i18n.language));
    } finally {
      setBusy(false);
    }
  }
  async function stop() {
    setBusy(true);
    try {
      await cancelTrainingJob(jobId);
      await refresh();
    } catch (error) {
      toast.error(getApiErrorMessage(error, t("studio.failed")));
    } finally {
      setBusy(false);
    }
  }
  const formatRuntime = useCallback(
    (seconds: number) => {
      const totalMinutes = Math.round(seconds / 60);
      if (totalMinutes >= 60 && totalMinutes % 60 === 0) {
        const hours = totalMinutes / 60;
        return `${hours} ${hours === 1 ? t("studio.hour") : t("studio.hours")}`;
      }
      if (totalMinutes >= 60) {
        const hours = Math.floor(totalMinutes / 60);
        const mins = totalMinutes % 60;
        return `${hours} ${hours === 1 ? t("studio.hour") : t("studio.hours")} ${mins} ${t("studio.minutes")}`;
      }
      return `${totalMinutes} ${t("studio.minutes")}`;
    },
    [t],
  );

  const formatResourceUsage = useCallback(
    (keys: string[]) => {
      if (!usage?.resources) return null;
      const res = usage.resources.find((r) => keys.includes(r.resource));
      if (!res) return null;
      const used = formatQuotaDuration(res.used_seconds);
      const limit =
        res.limit_seconds != null
          ? formatQuotaDuration(res.limit_seconds)
          : t("quotaUnlimited", "Unlimited");
      return `${used} / ${limit}`;
    },
    [usage, t],
  );

  const cpuOptions = useMemo<SelectOption[]>(() => {
    if (selectedJob) {
      const cpuProfile = caps?.cpu_profiles.find(
        (p) =>
          p.vcpu === selectedJob.vcpu && p.memory_mb === selectedJob.memory_mb,
      );
      const resKeys = cpuProfile ? [`cpu_${cpuProfile.id}`, cpuProfile.id] : [];
      const hint = resKeys.length ? formatResourceUsage(resKeys) : null;
      return [
        {
          value: "snapshot",
          label: t("studio.cpuProfile", {
            cpu: selectedJob.vcpu,
            memory: selectedJob.memory_mb,
          }),
          hint: hint || undefined,
        },
      ];
    }
    return (caps?.cpu_profiles ?? []).map((item) => {
      const resKeys = [`cpu_${item.id}`, item.id];
      const hint = formatResourceUsage(resKeys);
      return {
        value: item.id,
        label: `${t(`studio.profiles.${item.id}`)} · ${t("studio.cpuProfile", { cpu: item.vcpu, memory: item.memory_mb })}`,
        hint: hint || undefined,
      };
    });
  }, [selectedJob, caps?.cpu_profiles, formatResourceUsage, t]);

  const selectedGpuLabel = useMemo(() => {
    if (!selectedJob) return "";
    if (selectedJob.local_gpu_id) {
      const dev = caps?.local_gpu?.devices.find(
        (d) => d.id === selectedJob.local_gpu_id,
      );
      const name = dev?.name ?? selectedJob.local_gpu_id;
      return dev?.memory_total_mib
        ? `${name} (${dev.memory_total_mib} MiB)`
        : name;
    }
    if (selectedJob.accelerator_model) {
      const model = selectedJob.accelerator_model;
      const vram = model === "t4" ? "16 GB" : model === "a10g" ? "24 GB" : "";
      return `NVIDIA ${model.toUpperCase()}${vram ? ` (${vram})` : ""}`;
    }
    return t("studio.cpuOnly");
  }, [selectedJob, caps?.local_gpu?.devices, t]);

  const gpuOptions = useMemo<SelectOption[]>(() => {
    if (selectedJob) {
      let resKeys: string[] = [];
      if (selectedJob.local_gpu_id) {
        resKeys = ["gpu_local", selectedJob.local_gpu_id, "local_gpu"];
      } else if (selectedJob.accelerator_model) {
        resKeys = [
          selectedJob.accelerator_model,
          `gpu_${selectedJob.accelerator_model}`,
        ];
      }
      const hint = resKeys.length ? formatResourceUsage(resKeys) : null;
      return [
        { value: "snapshot", label: selectedGpuLabel, hint: hint || undefined },
      ];
    }
    return accelerators.map((item) => {
      const val = gpuKey(item);
      if (item.type === "none") {
        return { value: val, label: t("studio.cpuOnly") };
      }
      let resKeys: string[] = [];
      let label: string;
      if (item.device_id) {
        const dev = caps?.local_gpu?.devices.find(
          (d) => d.id === item.device_id,
        );
        const name = dev?.name ?? item.device_id;
        const vram = dev?.memory_total_mib
          ? ` (${dev.memory_total_mib} MiB)`
          : "";
        label = `${name}${vram}`;
        resKeys = ["gpu_local", item.device_id, "local_gpu"];
      } else {
        const model = item.model;
        const vram = model === "t4" ? "16 GB" : model === "a10g" ? "24 GB" : "";
        label = `NVIDIA ${model === "t4" ? "T4" : model === "a10g" ? "A10G" : (model ?? "GPU")}${vram ? ` (${vram})` : ""} ×1`;
        if (model) {
          resKeys = [model, `gpu_${model}`];
        }
      }
      const hint = resKeys.length ? formatResourceUsage(resKeys) : null;
      return {
        value: val,
        label,
        hint: hint || undefined,
      };
    });
  }, [
    selectedJob,
    selectedGpuLabel,
    accelerators,
    caps?.local_gpu?.devices,
    formatResourceUsage,
    t,
  ]);

  const runtimeOptions = useMemo<SelectOption[]>(() => {
    if (selectedJob) {
      return [
        {
          value: String(selectedJob.max_runtime_seconds),
          label:
            selectedJob.max_runtime_seconds == null
              ? t("studio.loading")
              : formatRuntime(selectedJob.max_runtime_seconds),
        },
      ];
    }
    return (caps?.runtime_options_seconds ?? []).map((seconds) => ({
      value: String(seconds),
      label: formatRuntime(seconds),
    }));
  }, [selectedJob, caps?.runtime_options_seconds, formatRuntime, t]);

  const frameworkOptions = useMemo<SelectOption[]>(() => {
    const flavors: Array<TrainingJobFormValues["model_flavor"]> = [
      "sklearn",
      "xgboost",
      "pytorch",
      "tensorflow",
    ];
    return flavors.map((value) => ({
      value,
      label: t(`table.flavors.${value}`),
    }));
  }, [t]);

  const cpuLimitCores =
    latestMetric?.cpu_limit_cores ?? workspace?.vcpu ?? cpu?.vcpu;
  const cpuUsedCores =
    latestMetric?.cpu_percent != null && cpuLimitCores != null
      ? Number(((latestMetric.cpu_percent / 100) * cpuLimitCores).toFixed(1))
      : null;
  const cpuUsageValue =
    latestMetric?.cpu_percent != null
      ? `${formatNumber(Math.round(latestMetric.cpu_percent), i18n.language)}%`
      : "-";
  const cpuUsageHelper =
    cpuLimitCores != null
      ? cpuUsedCores != null
        ? `${formatNumber(cpuUsedCores, i18n.language, { maximumFractionDigits: 1 })} / ${cpuLimitCores} vCPU`
        : `- / ${cpuLimitCores} vCPU`
      : t("studio.metrics.waiting");
  const cpuUsageTone =
    latestMetric?.cpu_percent != null && latestMetric.cpu_percent > 85
      ? "warning"
      : "default";

  const totalRamMb =
    latestMetric?.memory_limit_mb ??
    workspace?.memory_mb ??
    workspace?.memory_mb ??
    cpu?.memory_mb;
  const ramUsageValue =
    latestMetric?.memory_percent != null
      ? `${formatNumber(Math.round(latestMetric.memory_percent), i18n.language)}%`
      : latestMetric?.memory_used_mb != null && totalRamMb != null
        ? `${formatNumber(Math.round((latestMetric.memory_used_mb / totalRamMb) * 100), i18n.language)}%`
        : "-";
  const ramUsageHelper =
    totalRamMb != null
      ? latestMetric?.memory_used_mb != null
        ? `${formatMegabytes(latestMetric.memory_used_mb, i18n.language)} / ${formatMegabytes(totalRamMb, i18n.language)}`
        : `- / ${formatMegabytes(totalRamMb, i18n.language)}`
      : t("studio.metrics.waiting");
  const ramUsageTone =
    latestMetric?.memory_percent != null && latestMetric.memory_percent > 85
      ? "warning"
      : "default";

  const hasGpu = Boolean(
    workspace?.accelerator_type === "gpu" ||
    workspace?.local_gpu_id ||
    workspace?.accelerator_model ||
    (gpu && gpu !== "none"),
  );
  const totalGpuVramMb = useMemo(() => {
    if (selectedJob?.local_gpu_id) {
      const dev = caps?.local_gpu?.devices.find(
        (d) => d.id === selectedJob.local_gpu_id,
      );
      return dev?.memory_total_mib ?? null;
    }
    if (accelerator?.device_id) {
      const dev = caps?.local_gpu?.devices.find(
        (d) => d.id === accelerator.device_id,
      );
      return dev?.memory_total_mib ?? null;
    }
    const model = selectedJob?.accelerator_model || accelerator?.model;
    if (model === "t4") return 16384;
    if (model === "a10g") return 24576;
    return null;
  }, [selectedJob, accelerator, caps?.local_gpu?.devices]);

  const totalVramMb = latestMetric?.gpu_memory_total_mb ?? totalGpuVramMb;
  const gpuUsageValue = hasGpu
    ? latestMetric?.gpu_percent != null
      ? `${formatNumber(Math.round(latestMetric.gpu_percent), i18n.language)}%`
      : "-"
    : t("studio.cpuOnly");
  const gpuUsageHelper = hasGpu
    ? latestMetric?.gpu_memory_used_mb != null && totalVramMb != null
      ? `${formatMegabytes(latestMetric.gpu_memory_used_mb, i18n.language)} / ${formatMegabytes(totalVramMb, i18n.language)}`
      : totalVramMb != null
        ? `- / ${formatMegabytes(totalVramMb, i18n.language)}`
        : selectedGpuLabel || t("studio.metrics.waiting")
    : t("studio.metrics.noGpuAssigned");
  const gpuUsageTone =
    latestMetric?.gpu_percent != null && latestMetric.gpu_percent > 85
      ? "warning"
      : "default";

  const totalMaxRuntime = workspace?.max_runtime_seconds ?? maxRuntime ?? 86400;
  const runtimePct =
    currentElapsed != null && totalMaxRuntime > 0
      ? Math.min(100, Math.round((currentElapsed / totalMaxRuntime) * 100))
      : 0;
  const runtimeProgressValue = `${formatNumber(runtimePct, i18n.language)}%`;
  const runtimeProgressHelper = `${formatDurationLive(currentElapsed ?? 0)} / ${formatDurationLimit(totalMaxRuntime)}`;
  const runtimeProgressTone = runtimePct > 90 ? "warning" : "default";

  const isJobActive = Boolean(selectedJob?.submitted_at && active(selectedJob));
  const currentStatus = selectedJob?.status ?? workspace?.status;
  const statusBadge = currentStatus ? (
    <Badge
      variant={
        currentStatus === "completed"
          ? "success"
          : currentStatus === "failed"
            ? "danger"
            : currentStatus === "running" || currentStatus === "uploading"
              ? "primary"
              : ["cancelling", "cancelled"].includes(currentStatus)
                ? "warning"
                : ["pending", "queued"].includes(currentStatus)
                  ? "info"
                  : "neutral"
      }
    >
      {t(`detail.statuses.${currentStatus}`, currentStatus)}
    </Badge>
  ) : undefined;

  const runActionButton: TerminalActionItem = isJobActive
    ? {
        label: t("studio.stop"),
        icon: <Pause className="h-4 w-4" />,
        type: "danger",
        loading: busy && selectedJob?.status === "cancelling",
        disabled: busy || selectedJob?.status === "cancelling",
        onClick: () => void stop(),
      }
    : {
        label: t("studio.run"),
        icon: <Play className="h-4 w-4" />,
        type: "primary",
        loading: busy,
        disabled:
          locked ||
          savingConfig ||
          Boolean(saveError) ||
          !caps?.enabled ||
          !cpu ||
          !accelerator ||
          !workspace?.entry_point,
        onClick: () => void start(),
      };

  const handleBack = () => {
    if (params.get("step") === "project") {
      const next = new URLSearchParams(params);
      next.delete("step");
      setParams(next);
    } else {
      navigate("/dashboard/training");
    }
  };

  if (workspaceQuery.isError || jobQuery.isError)
    return (
      <div className="space-y-3">
        <p>
          {getApiErrorMessage(
            workspaceQuery.error || jobQuery.error,
            t("studio.failed"),
          )}
        </p>
        <Button
          onClick={() => {
            void workspaceQuery.refetch();
            if (jobId) void jobQuery.refetch();
          }}
        >
          {t("studio.reload")}
        </Button>
      </div>
    );
  if (!workspace || (jobId && !selectedJob))
    return <p className="p-5 text-style-body">{t("studio.loading")}</p>;

  return (
    <section className="space-y-5">
      <PageHeader
        title={t("studio.title")}
        back
        onBack={handleBack}
        actions={
          <Button variant="secondary" onClick={() => setHistoryOpen(true)}>
            {t("workspaceHistory.open", { count: draft?.job_count ?? 0 })}
          </Button>
        }
      />
      {params.get("step") === "project" &&
      selectedJob?.status === "completed" &&
      selectedJob.output_available ? (
        <TrainingProjectAssignment
          key={selectedJob.id}
          job={selectedJob}
          suggestedProject={params.get("project") ?? undefined}
          onBack={() => {
            const next = new URLSearchParams(params);
            next.delete("step");
            setParams(next);
          }}
          onSaved={(job) => {
            void queryClient.invalidateQueries({ queryKey: ["models"] });
            void queryClient.invalidateQueries({
              queryKey: trainingQueryKeys.jobs(),
            });
            navigate(`/dashboard/training/jobs/${job.id}/overview`);
          }}
        />
      ) : (
        <>
          <div className="space-y-4 rounded-surface border border-border bg-surface p-4">
            <div className="grid gap-4 sm:grid-cols-1 lg:grid-cols-2">
              <Select
                label={t("studio.cpu")}
                className="h-12 text-style-body"
                value={selectedJob ? "snapshot" : (cpu?.id ?? "")}
                disabled={locked}
                onChange={(val) => setCpuId(val)}
                options={cpuOptions}
              />
              <Select
                label={t("studio.gpu")}
                className="h-12 text-style-body"
                value={selectedJob ? "snapshot" : gpu}
                disabled={locked}
                onChange={(val) => setGpu(val)}
                options={gpuOptions}
              />
              <Select
                label={t("studio.runtime")}
                className="h-12 text-style-body"
                value={String(selectedJob?.max_runtime_seconds ?? maxRuntime)}
                disabled={locked}
                onChange={(val) => setRuntime(Number(val))}
                options={runtimeOptions}
              />
              <Select
                label={t("studio.framework")}
                className="h-12 text-style-body"
                value={selectedJob?.model_flavor ?? flavor}
                disabled={locked}
                onChange={(val) => setFlavor(val as typeof flavor)}
                options={frameworkOptions}
              />
            </div>
            {hasActiveRun && (
              <p className="text-style-caption text-color-warning">
                {t("studio.locked")}
              </p>
            )}
            {capsQuery.isError && (
              <p role="alert" className="text-style-caption text-color-danger">
                {t("studio.resourcesUnavailable")}
              </p>
            )}
          </div>
          {selectedJob?.submitted_at && snapshotQuery.isLoading ? (
            <p>{t("studio.loading")}</p>
          ) : selectedJob?.submitted_at && snapshotQuery.isError ? (
            <Button onClick={() => void snapshotQuery.refetch()}>
              {t("studio.reload")}
            </Button>
          ) : (
            <WorkspaceEditor
              key={`${selectedRun}:${reset}`}
              ref={editor}
              workspace={workspace}
              entries={
                jobId ? (snapshotQuery.data?.entries ?? []) : workspace.entries
              }
              outputs={selectedJob?.outputs ?? []}
              entryPoint={selectedJob?.entry_point ?? workspace.entry_point}
              runId={jobId || undefined}
              readOnly={!isDraft}
              externallyBusy={busy}
              onRefresh={refresh}
              onDirty={setDirty}
              onBusy={setEditorBusy}
              onOpenEnvironment={() => setEnvironmentOpen(true)}
              onDeleteOutputs={async () => {
                if (selectedJob) {
                  await deleteTrainingOutputs(selectedJob.id);
                  await jobQuery.refetch();
                  await refresh();
                }
              }}
            />
          )}
          {hasActiveRun && (
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <CardSummary
                label={t("studio.metrics.cpuUsage")}
                value={cpuUsageValue}
                helper={cpuUsageHelper}
                tone={cpuUsageTone}
                icon={<Cpu className="h-4 w-4" />}
              />
              <CardSummary
                label={t("studio.metrics.ramUsage")}
                value={ramUsageValue}
                helper={ramUsageHelper}
                tone={ramUsageTone}
                icon={<HardDrive className="h-4 w-4" />}
              />
              <CardSummary
                label={t("studio.metrics.gpuUsage")}
                value={gpuUsageValue}
                helper={gpuUsageHelper}
                tone={gpuUsageTone}
                icon={<Activity className="h-4 w-4" />}
              />
              <CardSummary
                label={t("studio.metrics.runtimeProgress")}
                value={runtimeProgressValue}
                helper={runtimeProgressHelper}
                tone={runtimeProgressTone}
                icon={<Clock className="h-4 w-4" />}
              />
            </div>
          )}
          <div id="training-terminal" />
          <TerminalViewer
            title={t("studio.terminal")}
            badge={statusBadge}
            logs={logStream.logs}
            bodyClassName="h-96 max-h-[45vh] min-h-72"
            placeholder={t("studio.logPlaceholder")}
            actionButtons={[runActionButton]}
          />
          {selectedJob?.error_message && (
            <p role="alert" className="text-style-body text-color-danger">
              {selectedJob.error_message}
            </p>
          )}
          <div className="grid grid-cols-2 gap-4">
            <Button
              type="button"
              variant="secondary"
              fullWidth
              onClick={() => navigate("/dashboard/training")}
            >
              {t("studio.close")}
            </Button>
            <Button
              type="button"
              variant="primary"
              fullWidth
              disabled={
                selectedJob?.status !== "completed" ||
                !selectedJob.output_available
              }
              onClick={() => {
                const next = new URLSearchParams(params);
                next.set("step", "project");
                setParams(next);
              }}
            >
              {t("studio.next")}
            </Button>
          </div>
        </>
      )}
      {historyOpen && (
        <TrainingJobDialog
          workspaceId={workspaceId}
          currentJobId={jobId || undefined}
          onClose={() => setHistoryOpen(false)}
        />
      )}
      {!jobId && draft?.active_job_id && (
        <Button
          onClick={() =>
            navigate(
              "/dashboard/training/workspaces/" +
                workspaceId +
                "/jobs/" +
                draft.active_job_id,
            )
          }
        >
          {t("workspaceHistory.openActive")}
        </Button>
      )}
      {environmentOpen && (
        <VariablesSecretDialog
          workspace={workspace}
          readOnly={Boolean(jobId)}
          onRefresh={refresh}
          onClose={() => setEnvironmentOpen(false)}
        />
      )}
      <ConfirmDialog
        open={blocker.state === "blocked"}
        title={t("studio.unsaved")}
        description={t("studio.discard")}
        confirmText={t("studio.cancel")}
        tone="danger"
        onCancel={() => {
          if (blocker.state === "blocked") blocker.reset();
        }}
        onConfirm={() => {
          setDirty(false);
          setReset((current) => current + 1);
          if (blocker.state === "blocked") blocker.proceed();
        }}
      />
    </section>
  );
}
