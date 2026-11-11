import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useBlocker, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Pause, Play } from "lucide-react";
import { Button } from "@/shared/components/Button";
import { PageHeader } from "@/shared/components/PageHeader";
import { ConfirmDialog } from "@/shared/components/ConfirmDialog";
import { Select, type SelectOption } from "@/shared/components/Select";
import { TerminalViewer, type TerminalActionItem } from "@/shared/components/TerminalViewer";
import { useRuntimeLogStream } from "@/shared/hooks/useRuntimeLogStream";
import { getApiErrorMessage } from "@/shared/api/errors";
import { toast } from "@/shared/lib/toastStore";
import { getTrainingStartError } from "@/features/training/api/quotaErrors";
import { cancelTrainingJob, cloneTrainingJob, deleteTrainingOutputs, getTrainingRuntimeCapabilities } from "@/features/training/api/trainingApi";
import { getRunInput, getJobWorkspace, updateJobWorkspace, runJob } from "@/features/training/api/jobWorkspaceApi";
import { WorkspaceEditor, type WorkspaceEditorHandle } from "@/features/training/components/WorkspaceEditor";
import { WorkspaceEnvironmentDialog } from "@/features/training/components/WorkspaceEnvironmentDialog";
import { TrainingProjectAssignment } from "@/features/training/components/TrainingProjectAssignment";
import { trainingQueryKeys } from "@/features/training/queryKeys";
import type { TrainingJob, TrainingJobFormValues } from "@/features/training/types";

const active = (job: TrainingJob) => ["pending", "queued", "running", "uploading", "cancelling"].includes(job.status);
const gpuKey = (item: { type: string; device_id?: string; model?: string }) => item.type === "none" ? "none" : item.device_id || item.model || "gpu";
export default function TrainingWorkspacePage() {
  const { jobId = "" } = useParams();
  return <TrainingJobWorkspace key={jobId} />;
}

function TrainingJobWorkspace() {
  const { jobId = "" } = useParams(); const [params, setParams] = useSearchParams();
  const navigate = useNavigate(); const queryClient = useQueryClient(); const { t, i18n } = useTranslation("training");
  const workspaceKey = ["training", "workspace", jobId];
  const workspaceQuery = useQuery({ queryKey: workspaceKey, queryFn: () => getJobWorkspace(jobId), refetchInterval: (query) => query.state.data && active(query.state.data) ? 3000 : false });
  const capsQuery = useQuery({ queryKey: ["training", "workspace-capabilities"], queryFn: () => getTrainingRuntimeCapabilities() });
  const [busy, setBusy] = useState(false); const [editorBusy, setEditorBusy] = useState(false); const [dirty, setDirty] = useState(false);
  const [environmentOpen, setEnvironmentOpen] = useState(false);
  const [cpuId, setCpuId] = useState(""); const [gpu, setGpu] = useState("none");
  const [runtime, setRuntime] = useState<number | null>(null); const [flavor, setFlavor] = useState<TrainingJobFormValues["model_flavor"]>("sklearn");
  const [saveError, setSaveError] = useState(""); const [savingConfig, setSavingConfig] = useState(false);
  const [reset, setReset] = useState(0);
  const editor = useRef<WorkspaceEditorHandle>(null); const allowNavigation = useRef(false);
  const runKey = useRef<string | null>(null); const cloneKey = useRef<string | null>(null);
  const saveQueue = useRef<Promise<void>>(Promise.resolve());
  const initialized = useRef("");
  const workspace = workspaceQuery.data;
  const isDraft = workspace?.status === "editing";
  const selectedJob = isDraft ? undefined : workspace;
  const selectedRun = jobId;
  const snapshotQuery = useQuery({ queryKey: ["training", "input", jobId], queryFn: () => getRunInput(jobId), enabled: Boolean(workspace?.submitted_at) });
  const hasActiveRun = Boolean(workspace && active(workspace));
  const locked = busy || editorBusy || hasActiveRun || !isDraft;
  const logStream = useRuntimeLogStream({ source: workspace?.submitted_at ? { kind: "training", id: jobId } : null, enabled: Boolean(workspace?.submitted_at), terminalStatuses: ["completed", "failed", "cancelled"] });
  const refresh = useCallback(async () => {
    const data = await getJobWorkspace(jobId); queryClient.setQueryData(["training", "workspace", jobId], data); return data;
  }, [queryClient, jobId]);
  const caps = capsQuery.data;
  useEffect(() => {
    if (!workspace || !caps || initialized.current === jobId) return;
    initialized.current = jobId;
    const chosen = caps.cpu_profiles.find((item) => item.vcpu === workspace.vcpu && item.memory_mb === workspace.memory_mb);
    setCpuId(chosen?.id ?? (workspace.vcpu ? "unavailable" : (caps.cpu_profiles.find((item) => item.id === "medium") ?? caps.cpu_profiles[0])?.id ?? ""));
    setGpu(workspace.accelerator_type === "gpu" ? workspace.local_gpu_id || workspace.accelerator_model : "none");
    setRuntime(workspace.max_runtime_seconds ?? caps.runtime_options_seconds?.at(-1) ?? 86400);
    setFlavor(workspace.model_flavor);
  }, [workspace, caps, jobId]);
  const cpu = caps?.cpu_profiles.find((item) => item.id === cpuId);
  const accelerators = useMemo(() => caps?.accelerators ?? [], [caps?.accelerators]);
  const accelerator = accelerators.find((item) => gpuKey(item) === gpu);
  const maxRuntime = runtime ?? caps?.runtime_options_seconds?.at(-1) ?? 86400;
  const settingsValue = useMemo(() => cpu && accelerator ? {
    model_flavor: flavor, vcpu: cpu.vcpu, memory_mb: cpu.memory_mb, max_runtime_seconds: maxRuntime,
    accelerator_type: accelerator.type, accelerator_count: accelerator.type === "gpu" ? 1 : 0,
    accelerator_model: accelerator.model ?? "", local_gpu_id: accelerator.device_id ?? "",
  } : null, [cpu, accelerator, flavor, maxRuntime]);
  const configDirty = Boolean(isDraft && settingsValue && workspace && !Object.entries(settingsValue).every(([key, value]) => workspace[key as keyof typeof workspace] === value));
  const blocker = useBlocker(({ currentLocation, nextLocation }) => (dirty || configDirty) && !allowNavigation.current && `${currentLocation.pathname}${currentLocation.search}` !== `${nextLocation.pathname}${nextLocation.search}`);
  useEffect(() => {
    if (!dirty && !configDirty) return;
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ""; };
    window.addEventListener("beforeunload", warn); return () => window.removeEventListener("beforeunload", warn);
  }, [dirty, configDirty]);
  const persistSettings = useCallback(async () => {
    if (!settingsValue) return;
    const revision = await editor.current?.saveAll();
    const current = await refresh();
    if (current.status !== "editing") return;
    if (Object.entries(settingsValue).every(([key, value]) => current[key as keyof typeof current] === value)) return;
    await updateJobWorkspace(jobId, revision ?? current.revision, settingsValue);
    await refresh();
  }, [settingsValue, jobId, refresh]);
  useEffect(() => {
    if (!isDraft || !settingsValue || initialized.current !== jobId) return;
    const timer = setTimeout(() => {
      setSavingConfig(true);
      saveQueue.current = saveQueue.current.catch(() => {}).then(persistSettings).then(() => setSaveError("")).catch((error: unknown) => {
        setSaveError(getApiErrorMessage(error, t("studio.failed")));
      }).finally(() => setSavingConfig(false));
    }, 400);
    return () => clearTimeout(timer);
  }, [isDraft, settingsValue, persistSettings, jobId, t]);
  async function start() {
    if (!workspace || !cpu || !accelerator || !isDraft) return;
    setBusy(true);
    try {
      await saveQueue.current;
      await persistSettings();
      const revision = await editor.current!.saveAll();
      runKey.current ??= crypto.randomUUID();
      const job = await runJob(jobId, revision, runKey.current);
      setDirty(false); setSaveError("");
      queryClient.setQueryData(workspaceKey, { ...workspace, ...job });
      await refresh();
      void queryClient.invalidateQueries({ queryKey: trainingQueryKeys.jobs() }); void queryClient.invalidateQueries({ queryKey: trainingQueryKeys.usage() });
    } catch (error) { toast.error(getTrainingStartError(error, t, i18n.language)); }
    finally { setBusy(false); }
  }
  async function stop() {
    setBusy(true);
    try { await cancelTrainingJob(jobId); await refresh(); }
    catch (error) { toast.error(getApiErrorMessage(error, t("studio.failed"))); }
    finally { setBusy(false); }
  }
  async function clone() {
    setBusy(true); cloneKey.current ??= crypto.randomUUID();
    try {
      const job = await cloneTrainingJob(jobId, cloneKey.current);
      void queryClient.invalidateQueries({ queryKey: trainingQueryKeys.jobs() });
      navigate(`/dashboard/training/${job.id}/workspace${workspace?.project_id ? `?project=${workspace.project_id}` : ""}`);
    } catch (error) { toast.error(getApiErrorMessage(error, t("studio.failed"))); }
    finally { setBusy(false); }
  }

  const formatRuntime = useCallback((seconds: number) => {
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
  }, [t]);

  const cpuOptions = useMemo<SelectOption[]>(() => {
    if (selectedJob) {
      return [{
        value: "snapshot",
        label: t("studio.cpuProfile", { cpu: selectedJob.vcpu, memory: selectedJob.memory_mb }),
      }];
    }
    return (caps?.cpu_profiles ?? []).map((item) => ({
      value: item.id,
      label: `${t(`studio.profiles.${item.id}`)} · ${t("studio.cpuProfile", { cpu: item.vcpu, memory: item.memory_mb })}`,
    }));
  }, [selectedJob, caps?.cpu_profiles, t]);

  const selectedGpuLabel = useMemo(() => {
    if (!selectedJob) return "";
    if (selectedJob.local_gpu_id) {
      const dev = caps?.local_gpu?.devices.find((d) => d.id === selectedJob.local_gpu_id);
      const name = dev?.name ?? selectedJob.local_gpu_id;
      return dev?.memory_total_mib ? `${name} (${dev.memory_total_mib} MiB)` : name;
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
      return [{ value: "snapshot", label: selectedGpuLabel }];
    }
    return accelerators.map((item) => {
      const val = gpuKey(item);
      if (item.type === "none") {
        return { value: val, label: t("studio.cpuOnly") };
      }
      if (item.device_id) {
        const dev = caps?.local_gpu?.devices.find((d) => d.id === item.device_id);
        const name = dev?.name ?? item.device_id;
        const vram = dev?.memory_total_mib ? ` (${dev.memory_total_mib} MiB)` : "";
        return { value: val, label: `${name}${vram}` };
      }
      const model = item.model;
      const vram = model === "t4" ? "16 GB" : model === "a10g" ? "24 GB" : "";
      return {
        value: val,
        label: `NVIDIA ${model === "t4" ? "T4" : model === "a10g" ? "A10G" : (model ?? "GPU")}${vram ? ` (${vram})` : ""} ×1`,
      };
    });
  }, [selectedJob, selectedGpuLabel, accelerators, caps?.local_gpu?.devices, t]);

  const runtimeOptions = useMemo<SelectOption[]>(() => {
    if (selectedJob) {
      return [{
        value: String(selectedJob.max_runtime_seconds),
        label: selectedJob.max_runtime_seconds == null ? t("studio.loading") : formatRuntime(selectedJob.max_runtime_seconds),
      }];
    }
    return (caps?.runtime_options_seconds ?? []).map((seconds) => ({
      value: String(seconds),
      label: formatRuntime(seconds),
    }));
  }, [selectedJob, caps?.runtime_options_seconds, formatRuntime, t]);

  const frameworkOptions = useMemo<SelectOption[]>(() => {
    const flavors: Array<TrainingJobFormValues["model_flavor"]> = ["sklearn", "xgboost", "pytorch", "tensorflow"];
    return flavors.map((value) => ({
      value,
      label: t(`table.flavors.${value}`),
    }));
  }, [t]);

  const isJobActive = Boolean(selectedJob?.submitted_at && active(selectedJob));
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
        disabled: locked || savingConfig || Boolean(saveError) || !caps?.enabled || !cpu || !accelerator || !workspace?.entry_point,
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

  if (workspaceQuery.isError) return <div className="space-y-3"><p>{getApiErrorMessage(workspaceQuery.error, t("studio.failed"))}</p><Button onClick={() => void workspaceQuery.refetch()}>{t("studio.reload")}</Button></div>;
  if (!workspace) return <p className="p-5 text-style-body">{t("studio.loading")}</p>;

  return <section className="space-y-5">
    <PageHeader
      title={t("studio.title")}
      back
      onBack={handleBack}
      actions={workspace && ["completed", "failed", "cancelled"].includes(workspace.status) ? <div className="flex gap-2"><Button variant="secondary" disabled={busy} onClick={() => setEnvironmentOpen(true)}>{t("studio.environment")}</Button><Button variant="secondary" disabled={busy} onClick={() => void clone()}>{t("studio.clone")}</Button></div> : undefined}
    />
    {params.get("step") === "project" && selectedJob?.status === "completed" && selectedJob.output_available ?
      <TrainingProjectAssignment key={selectedJob.id} job={selectedJob} suggestedProject={params.get("project") ?? undefined} onBack={() => { const next = new URLSearchParams(params); next.delete("step"); setParams(next); }} onSaved={(job) => { void queryClient.invalidateQueries({ queryKey: ["models"] }); void queryClient.invalidateQueries({ queryKey: trainingQueryKeys.jobs() }); navigate(`/dashboard/training/jobs/${job.id}/overview`); }} /> : <>
      <div className="space-y-4 rounded-surface border border-border bg-surface p-4">
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
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
        {isDraft && <p role="status" className="text-style-caption">{savingConfig ? t("studio.savingSettings") : saveError || t("studio.settingsSaved")}{saveError && <Button variant="secondary" onClick={() => { setSaveError(""); void persistSettings().catch((error: unknown) => setSaveError(getApiErrorMessage(error, t("studio.failed")))); }}>{t("studio.reload")}</Button>}</p>}
        {hasActiveRun && <p className="text-style-caption text-color-warning">{t("studio.locked")}</p>}
        {capsQuery.isError && <p role="alert" className="text-style-caption text-color-danger">{t("studio.resourcesUnavailable")}</p>}
      </div>
      {workspace.submitted_at && snapshotQuery.isLoading ? <p>{t("studio.loading")}</p> : workspace.submitted_at && snapshotQuery.isError ? <Button onClick={() => void snapshotQuery.refetch()}>{t("studio.reload")}</Button> :
        <WorkspaceEditor
          key={`${selectedRun}:${reset}`}
          ref={editor}
          workspace={workspace}
          entries={workspace.submitted_at ? snapshotQuery.data?.entries ?? [] : workspace.entries}
          outputs={selectedJob?.outputs ?? []}
          entryPoint={selectedJob?.entry_point ?? workspace.entry_point}
          runId={workspace.submitted_at ? jobId : undefined}
          readOnly={hasActiveRun || !isDraft}
          externallyBusy={busy}
          onRefresh={refresh}
          onDirty={setDirty}
          onBusy={setEditorBusy}
          onOpenEnvironment={() => setEnvironmentOpen(true)}
          onDeleteOutputs={async () => {
            if (selectedJob) {
              await deleteTrainingOutputs(selectedJob.id);
              await refresh();
            }
          }}
        />}
      <TerminalViewer
        title={t("studio.terminal")}
        logs={logStream.logs}
        placeholder={t("studio.logPlaceholder")}
        actionButtons={[runActionButton]}
      />
      {selectedJob?.error_message && <p role="alert" className="text-style-body text-color-danger">{selectedJob.error_message}</p>}
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
          disabled={selectedJob?.status !== "completed" || !selectedJob.output_available}
          onClick={() => {
            const next = new URLSearchParams(params);
            next.set("step", "project");
            setParams(next);
          }}
        >
          {t("studio.next")}
        </Button>
      </div>
    </>}
    {environmentOpen && <WorkspaceEnvironmentDialog workspace={workspace} onRefresh={refresh} onClose={() => setEnvironmentOpen(false)} />}
    <ConfirmDialog open={blocker.state === "blocked"} title={t("studio.unsaved")} description={t("studio.discard")} confirmText={t("studio.cancel")} tone="danger" onCancel={() => { if (blocker.state === "blocked") blocker.reset(); }} onConfirm={() => { setDirty(false); setReset((current) => current + 1); if (blocker.state === "blocked") blocker.proceed(); }} />
  </section>;
}
