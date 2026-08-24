import { useEffect, useRef } from "react";
import { Clipboard, Database, Download, FileArchive, FileCode2, Rocket, Trash2 } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { SourceEditor } from "@/features/catalog/components/SourceEditor";
import { useTrainingJobDetailContext } from "@/features/training/trainingJobDetailContext";
import { useRuntimeLogStream } from "@/shared/hooks/useRuntimeLogStream";
import { Button } from "@/shared/components/Button";
import { PageBody } from "@/shared/components/PageBody";
import { TerminalViewer } from "@/shared/components/TerminalViewer";

const BUILD_TERMINAL_STATUSES = ["ready", "failed", "cancelled"] as const;

export default function TrainingJobArtifactsPage() {
  const { t } = useTranslation("training");
  const navigate = useNavigate();
  const {
    job,
    downloadingOutput,
    downloadOutput,
    buildingAndRegistering,
    buildAndRegister,
    requestDeleteOutputs,
    copyUri,
    refreshJob,
  } = useTrainingJobDetailContext();
  const buildActive = ["pending", "queued", "building"].includes(
    job.registration_build?.status || "",
  );

  return (
    <div className="animate-in space-y-6 fade-in duration-300">
      <div className="rounded-surface border border-primary/20 bg-primary-subtle p-5">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <p className="text-style-body-strong text-color-primary">
              {t("detail.registry.title")}
            </p>
            <p className="mt-1 text-style-body text-color-primary">
              {t("detail.registry.description")}
            </p>
          </div>
          {job.registration_build?.status === "ready" ? (
            <Button
              icon={<Rocket className="h-4 w-4" />}
              onClick={() =>
                navigate(`/dashboard/model-evolution/${job.project_id}`)
              }
            >
              {t("detail.registry.open")}
            </Button>
          ) : (
            <Button
              icon={<Rocket className="h-4 w-4" />}
              loading={buildingAndRegistering}
              disabled={
                job.status !== "completed" ||
                !job.output_available ||
                buildActive
              }
              onClick={buildAndRegister}
            >
              {buildActive
                ? t("detail.registry.building")
                : job.registration_build
                  ? t("detail.registry.retry")
                  : t("detail.registry.build")}
            </Button>
          )}
        </div>
        {job.registration_build && (
          <div className="mt-5">
            <RegistrationBuildTerminal
              buildId={job.registration_build.id}
              title={t("detail.registry.console")}
              onCompleted={() => void refreshJob()}
            />
          </div>
        )}
      </div>

      <PageBody
        title={
          <div className="flex w-full flex-wrap items-center justify-between gap-4">
            <div className="flex items-center gap-2">
              <FileArchive className="h-5 w-5" />
              <h3 className="text-style-heading">{t("detail.artifactPage.title")}</h3>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button
                size="sm"
                icon={<Download className="h-4 w-4" />}
                disabled={!job.output_available}
                loading={downloadingOutput}
                onClick={downloadOutput}
              >
                {t("detail.artifactPage.download")}
              </Button>
              <Button
                size="sm"
                icon={<Trash2 className="h-4 w-4" />}
                variant="danger"
                disabled={!job.output_available}
                onClick={requestDeleteOutputs}
              >
                {t("detail.artifactPage.delete")}
              </Button>
            </div>
          </div>
        }
      >
        <div className="space-y-6 p-6">
          {job.output_available ? (
            <>
              <ArtifactUri
                heading={t("detail.artifactPage.modelHeading")}
                label={t("detail.artifactPage.modelLabel")}
                value={job.model_artifact_uri}
                onCopy={copyUri}
              />
              <ArtifactUri
                heading={t("detail.artifactPage.outputHeading")}
                label={t("detail.artifactPage.outputLabel")}
                value={job.output_s3_uri}
                onCopy={copyUri}
              />
            </>
          ) : (
            <div className="py-10 text-center">
              <FileArchive className="mx-auto mb-4 h-10 w-10 text-color-muted-foreground" />
              <p className="text-style-heading text-color-muted-foreground">
                {t("detail.artifactPage.notReady")}
              </p>
              <p className="mx-auto mt-1 max-w-sm text-style-body text-color-muted-foreground">
                {t("detail.artifactPage.notReadyDescription")}
              </p>
            </div>
          )}
        </div>
      </PageBody>

      <SourceEditor
        modelId={job.project_id}
        fileType="code_file"
        title={t("createFlow.source.sourceCode")}
        icon={<FileCode2 className="h-4 w-4" />}
        accept=".zip,.py,.json,.yaml,.yml"
        editorType="code"
        currentEntryPoint={job.entry_point}
      />
      
      <SourceEditor
        modelId={job.project_id}
        fileType="data_file"
        title={t("createFlow.source.referenceData")}
        icon={<Database className="h-4 w-4" />}
        accept=".zip,.csv,.parquet"
        editorType="csv"
      />
    </div>
  );
}

function RegistrationBuildTerminal({
  buildId,
  title,
  onCompleted,
}: {
  buildId: string;
  title: string;
  onCompleted: () => void;
}) {
  const handledStatus = useRef<string | null>(null);
  const stream = useRuntimeLogStream({
    source: { kind: "build", id: buildId },
    terminalStatuses: BUILD_TERMINAL_STATUSES,
  });

  useEffect(() => {
    if (
      stream.status &&
      BUILD_TERMINAL_STATUSES.includes(
        stream.status as (typeof BUILD_TERMINAL_STATUSES)[number],
      ) &&
      handledStatus.current !== stream.status
    ) {
      handledStatus.current = stream.status;
      onCompleted();
    }
  }, [onCompleted, stream.status]);

  return (
    <TerminalViewer
      title={title}
      logs={
        stream.error ? [...stream.logs, `Error: ${stream.error}`] : stream.logs
      }
    />
  );
}

function ArtifactUri({
  heading,
  label,
  value,
  onCopy,
}: {
  heading: string;
  label: string;
  value: string;
  onCopy: (value: string) => void;
}) {
  const { t } = useTranslation("training");
  return (
    <div className="space-y-2">
      <p className="text-style-overline uppercase text-color-muted-foreground">
        {heading}
      </p>
      <div className="flex w-full min-w-0 items-center justify-between gap-3 rounded-surface border border-border bg-muted px-4 py-2 shadow-sm">
        <div className="min-w-0 flex-1">
          <p className="text-style-caption font-bold uppercase text-color-muted-foreground">
            {label}
          </p>
          <code
            className="mt-1 block max-w-50 truncate font-mono text-style-code-sm text-color-foreground sm:max-w-md sm:text-style-body lg:max-w-xl"
            title={value || "-"}
          >
            {value || "-"}
          </code>
        </div>
        <button
          type="button"
          className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-surface border border-border bg-surface text-color-muted-foreground shadow-sm transition-all hover:bg-muted hover:text-color-foreground disabled:opacity-40"
          disabled={!value}
          onClick={() => onCopy(value)}
          aria-label={t("detail.artifactPage.copy", { label })}
        >
          <Clipboard className="h-4 w-4" />
        </button>
      </div>
    </div>
  );
}
