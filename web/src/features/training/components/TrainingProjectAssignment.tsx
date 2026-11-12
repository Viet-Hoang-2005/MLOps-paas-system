import { useEffect, useRef, useState } from "react";
import { isAxiosError } from "axios";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { listModelProjects } from "@/shared/api/catalogApi";
import { Button } from "@/shared/components/Button";
import { Input } from "@/shared/components/Input";
import { Select } from "@/shared/components/Select";
import { FileDropzone } from "@/shared/components/FileDropzone";
import { getApiErrorMessage } from "@/shared/api/errors";
import { toast } from "@/shared/lib/toastStore";
import type { TrainingJob } from "@/features/training/types";
import { assignTrainingProject } from "@/features/training/api/jobWorkspaceApi";
import {
  getModelOutputSummary,
  patchModelOutput,
} from "@/features/training/api/trainingApi";

export function TrainingProjectAssignment({
  job,
  suggestedProject,
  onBack,
  onSaved,
}: {
  job: TrainingJob;
  suggestedProject?: string;
  onBack: () => void;
  onSaved: (job: TrainingJob) => void;
}) {
  const { t } = useTranslation("training");
  const queryClient = useQueryClient();
  const outputKey = ["training", "assignment-output", job.id];
  const outputQuery = useQuery({
    queryKey: outputKey,
    queryFn: () => getModelOutputSummary(job.id),
    staleTime: Infinity,
    refetchOnWindowFocus: false,
  });
  const { data: projects } = useQuery({
    queryKey: ["training", "assignment-projects"],
    queryFn: listModelProjects,
  });
  const [projectId, setProjectId] = useState(
    job.project_id ?? suggestedProject ?? "new",
  );
  const [newId] = useState(() => crypto.randomUUID());
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [access, setAccess] = useState<"private" | "public">("private");
  const [busy, setBusy] = useState(false);
  const [conflict, setConflict] = useState(false);
  const [files, setFiles] = useState<Record<string, File | null>>({});
  const slots = [
    "label_mapping",
    "input_schema",
    "metrics",
    "params",
    "model_insights",
    "feature_importance",
  ] as const;
  const [modelId, setModelId] = useState("");
  const [modes, setModes] = useState<Record<string, string>>({});
  const [choices, setChoices] = useState<Record<string, string>>({});
  const hydrated = useRef(false);
  useEffect(() => {
    if (!outputQuery.data || hydrated.current) return;
    hydrated.current = true;
    const selection = outputQuery.data.selection;
    setModelId(selection?.model_id ?? "");
    setChoices(selection?.artifacts ?? {});
    setModes(
      Object.fromEntries(
        Object.keys(selection?.artifacts ?? {}).map((key) => [key, "metadata"]),
      ),
    );
  }, [outputQuery.data]);
  const available = outputQuery.data?.available_outputs ?? [];
  const modelOptions = available
    .filter((a) => a.metadata.group === "model")
    .map((a) => ({
      value: a.id,
      label: a.relative_path,
      hint: `${a.size_bytes} bytes`,
    }));
  const metadataOptions = available
    .filter(
      (a) =>
        a.metadata.group === "metadata" &&
        a.relative_path.toLowerCase().endsWith(".json") &&
        a.size_bytes <= 1024 * 1024,
    )
    .map((a) => ({ value: a.id, label: a.relative_path }));
  const [removed, setRemoved] = useState<string[]>([]);
  const [buildRequirements, setBuildRequirements] = useState<string | null>(
    null,
  );
  const project = projects?.models.find((item) => item.id === projectId);
  async function save() {
    setBusy(true);
    try {
      let output = outputQuery.data;
      if (!output) throw new Error(t("studio.reload"));
      if (
        ["source_code", "reference_data"].some((kind) =>
          Boolean(files[kind]),
        ) ||
        removed.length ||
        buildRequirements !== null
      ) {
        output = await patchModelOutput(job.id, {
          output_revision: output.output_revision,
          source_code_file: files.source_code,
          reference_data_file: files.reference_data,
          remove_assets: removed,
          ...(buildRequirements !== null
            ? { build_requirements_text: buildRequirements }
            : {}),
        });
        queryClient.setQueryData(outputKey, output);
        setRemoved([]);
        setBuildRequirements(null);
      }
      const assigned = await assignTrainingProject(
        job.id,
        output.output_revision,
        projectId === "new"
          ? {
              new_project: {
                id: newId,
                name,
                description,
                access_mode: access,
              },
            }
          : { project_id: projectId },
        {
          modelId,
          artifacts: Object.fromEntries(
            slots
              .filter((slot) => modes[slot] === "metadata")
              .map((slot) => [slot, choices[slot]]),
          ),
          files: Object.fromEntries(
            slots
              .filter((slot) => modes[slot] === "upload")
              .map((slot) => [slot, files[slot]]),
          ),
        },
      );
      void queryClient.invalidateQueries({ queryKey: outputKey });
      onSaved(assigned);
    } catch (error) {
      if (isAxiosError(error) && error.response?.status === 409)
        setConflict(true);
      toast.error(getApiErrorMessage(error, t("studio.failed")));
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="space-y-5 rounded-surface border border-border bg-surface p-5">
      <h2 className="text-style-section-title">{t("studio.assignProject")}</h2>
      <p className="text-style-body text-color-muted-foreground">
        {t("studio.assignmentHint")}
      </p>
      <Select
        label={t("studio.project")}
        value={projectId}
        disabled={busy || Boolean(job.project_id)}
        onChange={setProjectId}
        options={[
          { value: "new", label: t("studio.newProject") },
          ...(projects?.models
            .filter((item) => item.is_active)
            .map((item) => ({ value: item.id, label: item.name })) ?? []),
        ]}
      />
      {projectId === "new" ? (
        <>
          <Input
            label={t("studio.name")}
            value={name}
            disabled={busy}
            onChange={(event) => setName(event.target.value)}
          />
          <Input
            label={t("studio.description")}
            value={description}
            disabled={busy}
            onChange={(event) => setDescription(event.target.value)}
          />
          <Select
            label={t("studio.access")}
            value={access}
            disabled={busy}
            onChange={(value) => setAccess(value as "private" | "public")}
            options={[
              { value: "private", label: t("studio.private") },
              { value: "public", label: t("studio.public") },
            ]}
          />
        </>
      ) : (
        <div className="rounded-surface border border-border p-4 text-style-body">
          <p>{project?.name}</p>
          <p>{project?.description}</p>
          <p>{project?.access_mode}</p>
          <p className="mt-2 text-color-muted-foreground">
            {t("studio.metadataReadOnly")}
          </p>
        </div>
      )}
      <Select
        label={t("studio.artifactSelection.model")}
        value={modelId}
        placeholder={t("studio.artifactSelection.chooseModel")}
        options={modelOptions}
        onChange={setModelId}
        disabled={busy}
      />
      <div className="grid gap-4 md:grid-cols-2">
        {slots.map((slot) => (
          <div key={slot} className="space-y-2">
            <Select
              label={t(`studio.artifactSelection.${slot}`)}
              value={modes[slot] ?? "none"}
              options={[
                { value: "none", label: t("studio.artifactSelection.none") },
                {
                  value: "metadata",
                  label: t("studio.artifactSelection.fromMetadata"),
                },
                {
                  value: "upload",
                  label: t("studio.artifactSelection.upload"),
                },
              ]}
              disabled={busy}
              onChange={(value) => {
                setModes((old) => ({ ...old, [slot]: value }));
                setChoices((old) => ({ ...old, [slot]: "" }));
                setFiles((old) => ({ ...old, [slot]: null }));
              }}
            />
            {modes[slot] === "metadata" && (
              <Select
                aria-label={`${t(`studio.artifactSelection.${slot}`)}: ${t("studio.artifactSelection.chooseMetadata")}`}
                value={choices[slot] ?? ""}
                placeholder={t("studio.artifactSelection.chooseMetadata")}
                options={metadataOptions}
                disabled={busy}
                onChange={(value) =>
                  setChoices((old) => ({ ...old, [slot]: value }))
                }
              />
            )}
            {modes[slot] === "upload" && (
              <FileDropzone
                accept=".json"
                title={
                  files[slot]?.name ?? t("studio.artifactSelection.upload")
                }
                subtitle={t("studio.artifactSelection.jsonLimit")}
                hasFile={Boolean(files[slot])}
                disabled={busy}
                onRemove={() => setFiles((old) => ({ ...old, [slot]: null }))}
                onChange={(file) =>
                  setFiles((old) => ({ ...old, [slot]: file }))
                }
              />
            )}
          </div>
        ))}
        {(["source_code", "reference_data"] as const).map((kind) => (
          <FileDropzone
            key={kind}
            accept={kind === "source_code" ? ".py" : ".csv"}
            title={
              files[kind]?.name ??
              outputQuery.data?.[kind]?.name ??
              t(`studio.${kind}`)
            }
            subtitle={t("studio.optionalArtifact")}
            hasFile={Boolean(files[kind] || outputQuery.data?.[kind])}
            disabled={busy}
            onRemove={() => {
              setFiles((old) => ({ ...old, [kind]: null }));
              setRemoved((old) => [...old, kind]);
            }}
            onChange={(file) => setFiles((old) => ({ ...old, [kind]: file }))}
          />
        ))}
      </div>
      <label className="block space-y-2 text-style-body-strong">
        <span>{t("studio.buildRequirements")}</span>
        <textarea
          className="min-h-28 w-full rounded-control border border-input bg-surface p-3 font-mono text-style-body"
          value={
            buildRequirements ??
            outputQuery.data?.build_requirements_text ??
            job.requirements_text
          }
          disabled={busy}
          onChange={(event) => setBuildRequirements(event.target.value)}
        />
      </label>
      {(outputQuery.isError || conflict) && (
        <Button
          variant="secondary"
          onClick={() => {
            void outputQuery.refetch().then((result) => {
              if (!result.data) return;
              const selection = result.data.selection;
              setModelId(selection?.model_id ?? "");
              setChoices(selection?.artifacts ?? {});
              setModes(
                Object.fromEntries(
                  Object.keys(selection?.artifacts ?? {}).map((key) => [
                    key,
                    "metadata",
                  ]),
                ),
              );
              setFiles({});
              setRemoved([]);
              setBuildRequirements(null);
              setConflict(false);
            });
          }}
        >
          {t("studio.reload")}
        </Button>
      )}
      <div className="flex justify-between gap-3">
        <Button variant="secondary" disabled={busy} onClick={onBack}>
          {t("studio.back")}
        </Button>
        <Button
          loading={busy}
          disabled={
            conflict ||
            !outputQuery.data?.can_edit ||
            !modelId ||
            slots.some((slot) =>
              modes[slot] === "metadata"
                ? !choices[slot]
                : modes[slot] === "upload"
                  ? !files[slot] ||
                    files[slot].size > 1024 * 1024 ||
                    !files[slot].name.toLowerCase().endsWith(".json")
                  : false,
            ) ||
            (projectId === "new" && !name.trim())
          }
          onClick={() => void save()}
        >
          {t("studio.save")}
        </Button>
      </div>
    </section>
  );
}
