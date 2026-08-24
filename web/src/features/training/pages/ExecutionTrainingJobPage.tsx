import { ArrowLeft, Check, Play, Square } from "lucide-react";
import { useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";

import { useCreateTrainingJob } from "@/features/training/trainingFlowContext";
import type { TrainingAcceleratorType } from "@/features/training/types";
import { useRuntimeLogStream } from "@/shared/hooks/useRuntimeLogStream";
import { Button } from "@/shared/components/Button";
import { Slider } from "@/shared/components/Slider";
import { StatePanel } from "@/shared/components/StatePanel";
import { StepTitle } from "@/shared/components/StepTitle";
import {
  TerminalActionButton,
  TerminalViewer,
} from "@/shared/components/TerminalViewer";
import { Picker } from "@/shared/components/Picker";

const runtimeOptions = [
  { label: "15m", value: 900 },
  { label: "30m", value: 1800 },
  { label: "1h", value: 3600 },
  { label: "2h", value: 7200 },
  { label: "6h", value: 21600 },
  { label: "12h", value: 43200 },
];

const TRAINING_TERMINAL_STATUSES = [
  "completed",
  "failed",
  "cancelled",
] as const;

export default function ExecutionTrainingJobPage() {
  const { t } = useTranslation("training");
  const flow = useCreateTrainingJob();
  const handledTerminalState = useRef("");
  const active =
    flow.job &&
    ["pending", "queued", "uploading", "running"].includes(flow.job.status);
  const profiles = flow.capabilities?.cpu_profiles ?? [];
  const trainingEnabled = flow.capabilities?.enabled ?? false;
  const accelerators = flow.capabilities?.accelerators ?? [
    { type: "none" as const, counts: [0] },
  ];
  const stream = useRuntimeLogStream({
    source: flow.job?.id ? { kind: "training", id: flow.job.id } : null,
    enabled: Boolean(flow.job),
    terminalStatuses: TRAINING_TERMINAL_STATUSES,
  });

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
        <StepTitle
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
            value={`${flow.executionForm.accelerator_type}-${flow.executionForm.accelerator_count}`}
            onChange={(val) => {
              const [type, count] = val.split("-");
              flow.setExecutionField(
                "accelerator_type",
                type as TrainingAcceleratorType,
              );
              flow.setExecutionField("accelerator_count", Number(count));
            }}
            className="gap-3 sm:grid-cols-2 lg:grid-cols-3"
            options={accelerators.flatMap((accelerator) =>
              accelerator.counts.map((count) => ({
                value: `${accelerator.type}-${count}`,
                title:
                  accelerator.type === "none"
                    ? t("createFlow.execution.cpuOnly")
                    : `GPU x${count}`,
                description: flow.capabilities?.backend ?? "-",
              })),
            )}
          />
        </div>

        <div>
          <p className="mb-2 text-style-body-strong text-color-foreground">
            {t("createFlow.execution.maxRuntime")}
          </p>
          <Slider
            options={runtimeOptions}
            value={flow.executionForm.max_runtime_seconds}
            onChange={(value) =>
              flow.setExecutionField("max_runtime_seconds", value)
            }
          />
        </div>

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
                disabled={flow.transitionState !== "idle"}
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
