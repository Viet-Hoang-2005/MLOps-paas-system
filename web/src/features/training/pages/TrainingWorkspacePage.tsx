import { useCallback, useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useBlocker, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Button } from "@/shared/components/Button";
import { PageHeader } from "@/shared/components/PageHeader";
import { ConfirmDialog } from "@/shared/components/ConfirmDialog";
import { TerminalViewer } from "@/shared/components/TerminalViewer";
import { useRuntimeLogStream } from "@/shared/hooks/useRuntimeLogStream";
import { getApiErrorMessage } from "@/shared/api/errors";
import { toast } from "@/shared/lib/toastStore";
import { getTrainingStartError } from "@/features/training/api/quotaErrors";
import { cancelTrainingJob, getTrainingRuntimeCapabilities } from "@/features/training/api/trainingApi";
import { downloadRunOutput, getRunInput, getWorkspace, listWorkspaceRuns, runWorkspace } from "@/features/training/api/workspacesApi";
import { WorkspaceEditor, type WorkspaceEditorHandle } from "@/features/training/components/WorkspaceEditor";
import { WorkspaceEnvironmentDialog } from "@/features/training/components/WorkspaceEnvironmentDialog";
import { TrainingProjectAssignment } from "@/features/training/components/TrainingProjectAssignment";
import { trainingQueryKeys } from "@/features/training/queryKeys";
import type { TrainingJob, TrainingJobFormValues } from "@/features/training/types";

const active = (job: TrainingJob) => ["queued", "running", "uploading", "cancelling"].includes(job.status);
export default function TrainingWorkspacePage() {
  const { workspaceId = "" } = useParams(); const [params, setParams] = useSearchParams();
  const navigate = useNavigate(); const queryClient = useQueryClient(); const { t, i18n } = useTranslation("training");
  const workspaceKey = ["training", "workspace", workspaceId];
  const runsKey = ["training", "workspace-runs", workspaceId];
  const workspaceQuery = useQuery({ queryKey: workspaceKey, queryFn: () => getWorkspace(workspaceId) });
  const runsQuery = useQuery({ queryKey: runsKey, queryFn: () => listWorkspaceRuns(workspaceId), refetchInterval: (query) => query.state.data?.some(active) ? 3000 : false });
  const capsQuery = useQuery({ queryKey: ["training", "workspace-capabilities"], queryFn: () => getTrainingRuntimeCapabilities() });
  const [busy, setBusy] = useState(false); const [editorBusy, setEditorBusy] = useState(false); const [dirty, setDirty] = useState(false);
  const [environmentOpen, setEnvironmentOpen] = useState(false);
  const [cpuId, setCpuId] = useState(""); const [gpu, setGpu] = useState("none");
  const [runtime, setRuntime] = useState<number | null>(null); const [flavor, setFlavor] = useState<TrainingJobFormValues["model_flavor"]>("sklearn");
  const [reset, setReset] = useState(0);
  const editor = useRef<WorkspaceEditorHandle>(null); const allowNavigation = useRef(false);
  const runKey = useRef<string | null>(null);
  const workspace = workspaceQuery.data;
  const selectedRun = params.get("run") ?? "draft";
  const selectedJob = runsQuery.data?.find((job) => job.id === selectedRun);
  const snapshotQuery = useQuery({ queryKey: ["training", "input", selectedJob?.id], queryFn: () => getRunInput(selectedJob!.id), enabled: Boolean(selectedJob) });
  const hasActiveRun = Boolean(runsQuery.data?.some(active));
  const isDraft = selectedRun === "draft";
  const locked = busy || editorBusy || hasActiveRun || !isDraft;
  const unsaved = dirty;
  const blocker = useBlocker(({ currentLocation, nextLocation }) => unsaved && !allowNavigation.current && `${currentLocation.pathname}${currentLocation.search}` !== `${nextLocation.pathname}${nextLocation.search}`);
  useEffect(() => {
    if (!unsaved) return;
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ""; };
    window.addEventListener("beforeunload", warn); return () => window.removeEventListener("beforeunload", warn);
  }, [unsaved]);
  const logStream = useRuntimeLogStream({ source: selectedJob ? { kind: "training", id: selectedJob.id } : null, enabled: Boolean(selectedJob), terminalStatuses: ["completed", "failed", "cancelled"] });
  const refresh = useCallback(async () => {
    const data = await getWorkspace(workspaceId); queryClient.setQueryData(["training", "workspace", workspaceId], data); return data;
  }, [queryClient, workspaceId]);
  const caps = capsQuery.data;
  const cpu = caps?.cpu_profiles.find((item) => item.id === cpuId) ?? (!cpuId ? caps?.cpu_profiles.find((item) => item.id === "medium") ?? caps?.cpu_profiles[0] : undefined);
  const accelerators = caps?.accelerators ?? [];
  const gpuKey = (item: typeof accelerators[number]) => item.type === "none" ? "none" : item.device_id || item.model || "gpu";
  const accelerator = accelerators.find((item) => gpuKey(item) === gpu);
  const localDevice = caps?.local_gpu?.devices.find((device) => device.id === gpu);
  const maxRuntime = runtime ?? caps?.runtime_options_seconds?.at(-1) ?? 86400;
  async function start() {
    if (!workspace || !cpu || !accelerator || hasActiveRun || !isDraft) return;
    setBusy(true);
    try {
      const revision = await editor.current!.saveAll();
      runKey.current ??= crypto.randomUUID();
      const job = await runWorkspace(workspaceId, revision, runKey.current, {
        model_flavor: flavor, entry_point: workspace.entry_point,
        requirements_text: "", vcpu: cpu.vcpu, memory: cpu.memory_mb, max_runtime_seconds: maxRuntime,
        accelerator_type: accelerator.type, accelerator_count: accelerator.type === "gpu" ? 1 : 0,
        accelerator_model: accelerator.model ?? "", local_gpu_id: accelerator.device_id ?? "", source_zip: null, training_data: null,
      });
      runKey.current = null; setDirty(false);
      queryClient.setQueryData<TrainingJob[]>(runsKey, (previous) => [job, ...(previous ?? []).filter((item) => item.id !== job.id)]);
      void queryClient.invalidateQueries({ queryKey: trainingQueryKeys.jobs() }); void queryClient.invalidateQueries({ queryKey: trainingQueryKeys.usage() });
      allowNavigation.current = true; const next = new URLSearchParams(params); next.set("run", job.id); next.delete("step"); setParams(next); allowNavigation.current = false;
    } catch (error) { toast.error(getTrainingStartError(error, t, i18n.language)); }
    finally { setBusy(false); }
  }
  async function stop() {
    if (!selectedJob) return;
    setBusy(true);
    try { await cancelTrainingJob(selectedJob.id); await runsQuery.refetch(); }
    catch (error) { toast.error(getApiErrorMessage(error, t("studio.failed"))); }
    finally { setBusy(false); }
  }
  function selectRun(value: string) { const next = new URLSearchParams(params); if (value === "draft") next.delete("run"); else next.set("run", value); next.delete("step"); setParams(next); }
  const formSelect = "h-12 w-full rounded-control border border-input bg-surface px-3 text-style-body text-color-foreground";
  if (workspaceQuery.isError) return <div className="space-y-3"><p>{getApiErrorMessage(workspaceQuery.error, t("studio.failed"))}</p><Button onClick={() => void workspaceQuery.refetch()}>{t("studio.reload")}</Button></div>;
  if (!workspace) return <p className="p-5 text-style-body">{t("studio.loading")}</p>;
  return <section className="space-y-5">
    <PageHeader title={t("studio.title")} />
    <div className="flex flex-wrap items-center gap-3 rounded-surface border border-border bg-surface p-4">
      <span className="text-style-body-strong">1. {t("studio.runStep")}</span><span className="text-color-muted-foreground">→</span><span className="text-style-body-strong">2. {t("studio.assignProject")}</span>
      <label className="ml-auto flex items-center gap-2 text-style-body"><span>{t("studio.history")}</span><select className={formSelect} value={selectedRun} disabled={busy} onChange={(event) => selectRun(event.target.value)}><option value="draft">{t("studio.draft")}</option>{runsQuery.data?.map((job, index) => <option key={job.id} value={job.id}>{`${(runsQuery.data?.length ?? 0) - index}. ${job.id} · ${job.status}`}</option>)}</select></label>
    </div>
    {params.get("step") === "project" && selectedJob?.status === "completed" && selectedJob.output_available ?
      <TrainingProjectAssignment key={selectedJob.id} job={selectedJob} suggestedProject={params.get("project") ?? undefined} onBack={() => { const next = new URLSearchParams(params); next.delete("step"); setParams(next); }} onSaved={(job) => { void queryClient.invalidateQueries({ queryKey: ["models"] }); void queryClient.invalidateQueries({ queryKey: trainingQueryKeys.jobs() }); navigate(`/dashboard/training/jobs/${job.id}/overview`); }} /> : <>
      <div className="space-y-4 rounded-surface border border-border bg-surface p-4">
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <label className="space-y-2 text-style-body-strong"><span>{t("studio.cpu")}</span><select className={formSelect} value={selectedJob ? "snapshot" : cpu?.id ?? ""} disabled={locked} onChange={(event) => setCpuId(event.target.value)}>{selectedJob ? <option value="snapshot">{t("studio.cpuProfile", { cpu: selectedJob.vcpu, memory: selectedJob.memory_mb })}</option> : caps?.cpu_profiles.map((item) => <option key={item.id} value={item.id}>{t(`studio.profiles.${item.id}`)} · {t("studio.cpuProfile", { cpu: item.vcpu, memory: item.memory_mb })}</option>)}</select></label>
          <label className="space-y-2 text-style-body-strong"><span>{t("studio.gpu")}</span><select className={formSelect} value={selectedJob ? "snapshot" : gpu} disabled={locked} onChange={(event) => setGpu(event.target.value)}>{selectedJob ? <option value="snapshot">{selectedJob.local_gpu_id || selectedJob.accelerator_model || t("studio.cpuOnly")}</option> : accelerators.map((item) => <option key={gpuKey(item)} value={gpuKey(item)}>{item.type === "none" ? t("studio.cpuOnly") : item.device_id ? caps?.local_gpu?.devices.find((device) => device.id === item.device_id)?.name ?? item.device_id : `NVIDIA ${item.model === "t4" ? "T4 16 GB" : "A10G 24 GB"} ×1`}</option>)}</select></label>
          <label className="space-y-2 text-style-body-strong"><span>{t("studio.runtime")}</span><select className={formSelect} value={selectedJob?.max_runtime_seconds ?? maxRuntime} disabled={locked} onChange={(event) => setRuntime(Number(event.target.value))}>{selectedJob ? <option value={selectedJob.max_runtime_seconds}>{selectedJob.max_runtime_seconds / 60} {t("studio.minutes")}</option> : caps?.runtime_options_seconds?.map((seconds) => <option key={seconds} value={seconds}>{seconds / 60} {t("studio.minutes")}</option>)}</select></label>
          <label className="space-y-2 text-style-body-strong"><span>{t("studio.framework")}</span><select className={formSelect} value={selectedJob?.model_flavor ?? flavor} disabled={locked} onChange={(event) => setFlavor(event.target.value as typeof flavor)}>{["sklearn", "xgboost", "pytorch", "tensorflow"].map((value) => <option key={value} value={value}>{t(`table.flavors.${value}`)}</option>)}</select></label>
        </div>
        <p className="text-style-caption text-color-muted-foreground">{t("studio.contract")}</p>
        {localDevice && <p className="text-style-caption">{localDevice.name} · {t("studio.vram", { total: localDevice.memory_total_mib ?? "—", free: localDevice.memory_free_mib ?? "—" })}</p>}
        {caps?.local_gpu && <p className="text-style-caption text-color-muted-foreground">{t(`studio.gpuStatus.${caps.local_gpu.status}`)} · {caps.local_gpu.checked_at ?? ""}</p>}
        <div className="flex flex-wrap gap-2"><Button variant="secondary" size="sm" disabled={locked} onClick={() => setEnvironmentOpen(true)}>{t("studio.environment")}</Button><Button variant="secondary" size="sm" disabled={busy || hasActiveRun} loading={capsQuery.isFetching} onClick={() => void getTrainingRuntimeCapabilities(true).then((data) => queryClient.setQueryData(["training", "workspace-capabilities"], data)).catch((error) => toast.error(getApiErrorMessage(error, t("studio.failed"))))}>{t("studio.checkResources")}</Button></div>
        {hasActiveRun && <p className="text-style-caption text-color-warning">{t("studio.locked")}</p>}
        {capsQuery.isError && <p role="alert" className="text-style-caption text-color-danger">{t("studio.resourcesUnavailable")}</p>}
      </div>
      {selectedJob && snapshotQuery.isLoading ? <p>{t("studio.loading")}</p> : selectedJob && snapshotQuery.isError ? <Button onClick={() => void snapshotQuery.refetch()}>{t("studio.reload")}</Button> :
        <WorkspaceEditor key={`${selectedRun}:${reset}`} ref={editor} workspace={workspace} entries={selectedJob ? snapshotQuery.data?.entries ?? [] : workspace.entries} entryPoint={selectedJob?.entry_point ?? workspace.entry_point} runId={selectedJob?.id} readOnly={hasActiveRun || !isDraft} externallyBusy={busy} onRefresh={refresh} onDirty={setDirty} onBusy={setEditorBusy} />}
      <TerminalViewer title={t("studio.terminal")} logs={logStream.logs} placeholder={t("studio.logPlaceholder")} actions={selectedJob && active(selectedJob) ? <Button variant="secondary" disabled={busy || selectedJob.status === "cancelling"} onClick={() => void stop()}>{t("studio.stop")}</Button> : <Button disabled={locked || !caps?.enabled || !cpu || !accelerator || !workspace.entry_point} loading={busy} onClick={() => void start()}>{t("studio.run")}</Button>} />
      {selectedJob?.error_message && <p role="alert" className="text-style-body text-color-danger">{selectedJob.error_message}</p>}
      {selectedJob && <div className="space-y-2 rounded-surface border border-border bg-surface p-4"><h2 className="text-style-body-strong">{t("studio.output")}</h2>{selectedJob.outputs.map((output) => <div key={output.id} className="flex items-center justify-between gap-3 text-style-body"><span>{output.relative_path}</span><Button variant="secondary" size="sm" onClick={() => void downloadRunOutput(selectedJob.id, output.id).then((url) => window.open(url, "_blank", "noopener,noreferrer")).catch((error) => toast.error(getApiErrorMessage(error, t("studio.failed"))))}>{t("studio.download")}</Button></div>)}{!selectedJob.outputs.length && <p className="text-style-caption text-color-muted-foreground">{t("studio.noOutput")}</p>}</div>}
      <div className="flex justify-between gap-3"><Button variant="secondary" onClick={() => navigate("/dashboard/training")}>{t("studio.close")}</Button><Button disabled={selectedJob?.status !== "completed" || !selectedJob.output_available} onClick={() => { const next = new URLSearchParams(params); next.set("step", "project"); setParams(next); }}>{t("studio.next")}</Button></div>
    </>}
    {environmentOpen && <WorkspaceEnvironmentDialog workspace={workspace} onRefresh={refresh} onClose={() => setEnvironmentOpen(false)} />}
    <ConfirmDialog open={blocker.state === "blocked"} title={t("studio.unsaved")} description={t("studio.discard")} confirmText={t("studio.close")} tone="danger" onCancel={() => { if (blocker.state === "blocked") blocker.reset(); }} onConfirm={() => { setDirty(false); setReset((current) => current + 1); if (blocker.state === "blocked") blocker.proceed(); }} />
  </section>;
}
