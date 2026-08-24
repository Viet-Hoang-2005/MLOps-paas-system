import { ArrowLeft, ArrowRight, Play, Square } from "lucide-react";
import { useEffect } from "react";
import { useTranslation } from "react-i18next";

import { BuildInputFields } from "@/features/deploy/components/BuildInputFields";
import { useUploadModel } from "@/features/deploy/uploadModelContext";
import { useRuntimeLogStream } from "@/shared/hooks/useRuntimeLogStream";
import { Button } from "@/shared/components/Button";
import {
  TerminalActionButton,
  TerminalViewer,
} from "@/shared/components/TerminalViewer";

const BUILD_TERMINAL_STATUSES = ["ready", "failed", "cancelled"] as const;

export default function BuildModelPage() {
  const { t } = useTranslation("deploy");
  const { t: tc } = useTranslation("common");
  const {
    buildForm,
    build,
    transitionState,
    setBuildField,
    startBuild,
    continueFromBuild,
    goToStep,
    refreshBuild,
  } = useUploadModel();
  const buildActive = Boolean(
    build && ["pending", "queued", "building"].includes(build.status),
  );
  const stream = useRuntimeLogStream({
    source: build?.id ? { kind: "build", id: build.id } : null,
    enabled: Boolean(build),
    terminalStatuses: BUILD_TERMINAL_STATUSES,
  });

  useEffect(() => {
    if (
      stream.status &&
      BUILD_TERMINAL_STATUSES.includes(
        stream.status as (typeof BUILD_TERMINAL_STATUSES)[number],
      )
    ) {
      void refreshBuild();
    }
  }, [refreshBuild, stream.status]);

  const terminalLogs = stream.error
    ? [...stream.logs, `${tc("terminal.error")} ${stream.error}`]
    : stream.logs;
  const startDisabled =
    transitionState !== "idle" || !buildForm.source_artifact;

  return (
    <>
      <div className="rounded-surface border border-border bg-surface p-6 lg:p-8">
        <BuildInputFields form={buildForm} setField={setBuildField} />
        <div className="mt-8 border-t border-border pt-8">
          <TerminalViewer
            key={build?.id ?? "new-build"}
            title={t("uploadFlow.build.console")}
            logs={terminalLogs}
            placeholder={t("uploadFlow.build.consolePlaceholder")}
            actions={
              buildActive ? (
                <TerminalActionButton
                  tone="danger"
                  icon={<Square className="h-3 w-3" />}
                  onClick={async () => {
                    if (!build) return;
                    const { cancelBuildById } =
                      await import("@/features/deploy/api/deployApi");
                    await cancelBuildById(build.id);
                    await refreshBuild();
                  }}
                >
                  {tc("terminal.stop")}
                </TerminalActionButton>
              ) : (
                <TerminalActionButton
                  icon={<Play className="h-4 w-4" />}
                  tone="start"
                  loading={transitionState === "starting-build"}
                  disabled={startDisabled}
                  onClick={() => void startBuild()}
                >
                  {build ? tc("terminal.rebuild") : tc("terminal.build")}
                </TerminalActionButton>
              )
            }
          />
        </div>
      </div>
      <footer className="grid gap-3 pb-6 sm:grid-cols-2">
        <Button
          variant="secondary"
          size="md"
          icon={<ArrowLeft className="h-4 w-4" />}
          disabled={transitionState !== "idle"}
          onClick={() => void goToStep(1)}
        >
          {t("uploadFlow.actions.back")}
        </Button>
        <Button
          size="md"
          disabled={transitionState !== "idle"}
          onClick={continueFromBuild}
        >
          {t("uploadFlow.actions.continue")} <ArrowRight className="h-4 w-4" />
        </Button>
      </footer>
    </>
  );
}
