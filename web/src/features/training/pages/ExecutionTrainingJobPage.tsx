import { ArrowLeft, Check, Play, Square } from "lucide-react";
import { useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";

import { useCreateTrainingJob } from "@/features/training/trainingFlowContext";
import type { TrainingAcceleratorType } from "@/features/training/types";
import { useRuntimeLogStream } from "@/shared/hooks/useRuntimeLogStream";
import { Button } from "@/shared/components/Button";
import { Slider } from "@/shared/components/Slider";
import { StatePanel } from "@/shared/components/StatePanel";
import { ExecutionObservation } from "@/shared/components/ExecutionObservation";
import { Title } from "@/shared/components/Title";
import {
  TerminalActionButton,
  TerminalViewer,
} from "@/shared/components/TerminalViewer";
import { Picker } from "@/shared/components/Picker";
import { useQuery } from "@tanstack/react-query";
import { getTrainingUsage } from "@/features/training/api/trainingApi";
import { trainingQueryKeys } from "@/features/training/queryKeys";
import { formatDuration } from "@/shared/lib/formatDuration";
import { formatQuotaDuration } from "@/features/training/api/quotaFormatting";

const runtimeOptions = [
  { label: "15m", value: 900 },
  { label: "30m", value: 1800 },
  { label: "1h", value: 3600 },
  { label: "2h", value: 7200 },
  { label: "6h", value: 21600 },
  { label: "12h", value: 43200 },
  { label: "24h", value: 86400 },
];

const TRAINING_TERMINAL_STATUSES = [
  "completed",
  "failed",
  "cancelled",
] as const;

export default function ExecutionTrainingJobPage() {
  const { t } = useTranslation("training");
  const flow = useCreateTrainingJob();
  const { data: usage, dataUpdatedAt: usageUpdatedAt, isError: usageError } = useQuery({ queryKey: trainingQueryKeys.usage(), queryFn: getTrainingUsage, refetchInterval: 15000 });
  const handledTerminalState = useRef("");
  const active =
    flow.job &&
    ["pending", "queued", "uploading", "running"].includes(flow.job.status);
  const profiles = flow.capabilities?.cpu_profiles ?? [];
  const quotaResource = flow.executionForm.accelerator_type === "gpu"
    ? (flow.capabilities?.backend === "docker" ? "gpu_local" : flow.executionForm.accelerator_model)
    : ({ 1: "cpu_small", 2: "cpu_medium", 4: "cpu_large" } as Record<number, string>)[flow.executionForm.vcpu];
  const quota = usage?.resources.find((item) => item.resource === quotaResource);
  const supportedRuntimeOptions = (
    flow.capabilities?.runtime_options_seconds ?? []
  ).map((value) => ({
    value,
    label:
      runtimeOptions.find((option) => option.value === value)?.label ??
      formatDuration(value),
  }));
  const observeExecution = Boolean(
    flow.job &&
    (["queued", "running", "uploading", "cancelling"].includes(
      flow.job.status,
    ) ||
      flow.job.observation_status === "cleanup_pending"),
  );
  const trainingEnabled = flow.capabilities?.enabled ?? false;
  const accelerators = flow.capabilities?.accelerators ?? [
    { type: "none" as const, counts: [0] },
  ];
  const localGpu = flow.capabilities?.local_gpu;
  const missingSelectedGpu = flow.capabilities?.backend === "docker" &&
    flow.executionForm.accelerator_type === "gpu" &&
    !localGpu?.devices.some((device) => device.id === flow.executionForm.local_gpu_id);
  const stream = useRuntimeLogStream({
    source: flow.job?.id ? { kind: "training", id: flow.job.id } : null,
    enabled: Boolean(flow.job),
    terminalStatuses: TRAINING_TERMINAL_STATUSES,
  });

  useEffect(() => {
    if (!observeExecution) return;
    const timer = window.setInterval(() => {
      void flow.refreshJob().catch(() => undefined);
    }, 4000);
    return () => window.clearInterval(timer);
  }, [flow, observeExecution]);

  useEffect(() => {
    const terminalKey = `${flow.job?.id ?? ""}:${stream.status ?? ""}`;
    if (
      stream.status &&
      TRAINING_TERMINAL_STATUSES.includes(
        stream.status as (typeof TRAINING_TERMINAL_STATUSES)[number],
      ) &&
      handledTerminalState.current !== terminalKey
    ) {
      handledTerminalState.current = terminalKey;
      void flow.refreshJob(stream.status);
    }
  }, [flow, stream.status]);

  if (!trainingEnabled) {
    return (
      <>
        <StatePanel
          title={t("createFlow.execution.unavailableTitle")}
          description={t("createFlow.execution.unavailableDescription")}
        />
        <footer className="grid gap-3 pb-6">
          <Button
            variant="secondary"
            icon={<ArrowLeft className="h-4 w-4" />}
            onClick={() => void flow.goToStep(2)}
          >
            {t("createFlow.actions.back")}
          </Button>
        </footer>
      </>
    );
  }

  return (
    <>
      <div className="space-y-6 rounded-surface border border-border bg-surface p-6">
        <Title
          title={t("createFlow.execution.title")}
          subtitle={t("createFlow.execution.description")}
        />
        <Picker
          value={`${flow.executionForm.vcpu}-${flow.executionForm.memory_mb}`}
          onChange={(val) => {
            const [vcpu, memory_mb] = val.split("-");
            flow.setExecutionField("vcpu", Number(vcpu));
            flow.setExecutionField("memory_mb", Number(memory_mb));
          }}
          className="md:grid-cols-3"
          options={profiles.map((profile) => ({
            value: `${profile.vcpu}-${profile.memory_mb}`,
            title: <span className="capitalize">{profile.id}</span>,
            description: `${profile.vcpu} vCPU / ${profile.memory_mb} MB`,
          }))}
        />

        <div className="space-y-3">
          <p className="text-style-body-strong text-color-foreground">
            {t("createFlow.execution.accelerator")}
          </p>
          <Picker
            value={`${flow.executionForm.accelerator_type}|${flow.executionForm.local_gpu_id || flow.executionForm.accelerator_model || "generic"}|${flow.executionForm.accelerator_count}`}
            onChange={(val) => {
              const [type, selection, count] = val.split("|");
              flow.setExecutionField(
                "accelerator_type",
                type as TrainingAcceleratorType,
              );
              flow.setExecutionField("accelerator_count", Number(count));
              flow.setExecutionField("accelerator_model", selection === "t4" || selection === "a10g" ? selection : "");
              flow.setExecutionField("local_gpu_id", selection.startsWith("GPU-") ? selection : "");
            }}
            className="gap-3 sm:grid-cols-2 lg:grid-cols-3"
            options={accelerators.flatMap((accelerator) =>
              accelerator.counts.map((count) => ({
                value: `${accelerator.type}|${accelerator.device_id || accelerator.model || "generic"}|${count}`,
                title:
                  accelerator.type === "none"
                    ? t("createFlow.execution.cpuOnly")
                    : accelerator.device_id
                      ? localGpu?.devices.find((device) => device.id === accelerator.device_id)?.name ?? t("createFlow.execution.gpuGeneric")
                    : accelerator.model === "t4"
                      ? t("createFlow.execution.gpuT4")
                      : accelerator.model === "a10g"
                        ? t("createFlow.execution.gpuA10g")
                        : t("createFlow.execution.gpuGeneric"),
                description: accelerator.device_id ? (() => {
                  const device = localGpu?.devices.find((item) => item.id === accelerator.device_id);
                  const total = device?.memory_total_mib;
                  const free = device?.memory_free_mib;
                  return t("createFlow.execution.gpuMemory", {
                    total: total == null ? t("createFlow.execution.gpuUnknown") : `${total} MiB`,
                    free: free == null ? t("createFlow.execution.gpuUnknown") : `${free} MiB`,
                  });
                })() : flow.capabilities?.backend ?? "-",
              })),
            )}
          />
          {localGpu && (
            <div className="space-y-2" role="status">
              <p className="text-style-body text-color-muted-foreground">
                {t(`createFlow.execution.gpuStatus.${localGpu.status}`)}
              </p>
              {localGpu.status === "available" && <p className="text-style-body text-color-muted-foreground">{t("createFlow.execution.gpuMemoryNote")}</p>}
              {localGpu.reason && <p className="text-style-body text-color-muted-foreground">
                {t(`createFlow.execution.gpuReason.${localGpu.reason}`)}
              </p>}
              {missingSelectedGpu && <p className="text-style-body text-color-danger">{t("createFlow.execution.gpuSelectionMissing")}</p>}
              <Button variant="secondary" loading={flow.gpuChecking} onClick={() => void flow.refreshGpuCapabilities()}>
                {t("createFlow.execution.gpuCheckAgain")}
              </Button>
            </div>
          )}
        </div>

        <div>
          <p className="mb-2 text-style-body-strong text-color-foreground">
            {t("createFlow.execution.maxRuntime")}
          </p>
          <Slider
            options={supportedRuntimeOptions}
            value={flow.executionForm.max_runtime_seconds}
            onChange={(value) =>
              flow.setExecutionField("max_runtime_seconds", value)
            }
          />
          {usage && quota && <p className="mt-2 text-style-caption text-color-muted-foreground">
            {t("createFlow.execution.quotaRemaining", { duration: quota.remaining_seconds == null ? t("quotaUnlimited") : formatQuotaDuration(quota.remaining_seconds) })}
          </p>}
          {usageError && <p className="mt-2 text-style-caption text-color-danger">{t("quotaUnavailable")}</p>}
          {usage?.backend === "argo" && usageUpdatedAt + (flow.executionForm.max_runtime_seconds + (flow.capabilities?.dispatch_timeout_seconds ?? 0)) * 1000 > Date.parse(usage.reset_at) &&
            <p className="mt-2 text-style-caption text-color-muted-foreground">{t("createFlow.execution.quotaCrossWeek")}</p>}
        </div>

        <ExecutionObservation state={flow.job} />
        <TerminalViewer
          key={flow.job?.id ?? "new-training"}
          title={t("createFlow.execution.console")}
          logs={
            stream.error
              ? [...stream.logs, `Error: ${stream.error}`]
              : stream.logs
          }
          placeholder={t("createFlow.execution.placeholder")}
          actions={
            active ? (
              <TerminalActionButton
                tone="danger"
                icon={<Square className="h-3 w-3" />}
                onClick={() => void flow.cancelTraining()}
              >
                {t("createFlow.execution.stop")}
              </TerminalActionButton>
            ) : (
              <TerminalActionButton
                icon={<Play className="h-3 w-3" />}
                loading={flow.transitionState === "starting-training"}
                disabled={flow.transitionState !== "idle" || flow.gpuChecking || missingSelectedGpu}
                onClick={() => void flow.startTraining()}
              >
                {flow.job
                  ? t("createFlow.execution.retrain")
                  : t("createFlow.execution.train")}
              </TerminalActionButton>
            )
          }
        />
      </div>

      <footer className="grid gap-3 pb-6 sm:grid-cols-2">
        <Button
          variant="secondary"
          icon={<ArrowLeft className="h-4 w-4" />}
          onClick={() => void flow.goToStep(2)}
        >
          {t("createFlow.actions.back")}
        </Button>
        <Button
          icon={<Check className="h-4 w-4" />}
          onClick={() => flow.finishTraining()}
        >
          {t("createFlow.actions.finish")}
        </Button>
      </footer>
    </>
  );
}
