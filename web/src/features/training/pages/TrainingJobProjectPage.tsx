import { useEffect, useRef, useState } from "react";
import { listModelProjects } from "@/shared/api/catalogApi";
import { Input } from "@/shared/components/Input";
import { Select } from "@/shared/components/Select";
import { FileDropzone } from "@/shared/components/FileDropzone";
import { ConfirmDialog } from "@/shared/components/ConfirmDialog";
import { toast } from "@/shared/lib/toastStore";
import { Title } from "@/shared/components/Title";
import { Badge } from "@/shared/components/Badge";
import { TextArea } from "@/shared/components/TextArea";
import { Picker } from "@/shared/components/Picker";
import { Callout } from "@/shared/components/Callout";
import type { TrainingJob } from "@/features/training/types";
import {
  assignTrainingProject,
  getWorkspaceJob,
  getRunInput,
  downloadWorkspaceSelection,
  listAllWorkspaceJobs,
} from "@/features/training/api/jobWorkspaceApi";
import {
  getModelOutputSummary,
  isTrainingRevisionConflict,
  patchModelOutput,
} from "@/features/training/api/trainingApi";

import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { trainingQueryKeys } from "@/features/training/queryKeys";
import { PageHeader } from "@/shared/components/PageHeader";
import { Button } from "@/shared/components/Button";
import { getApiErrorMessage } from "@/shared/api/errors";

const getJobStatusVariant = (
  status: string,
): "success" | "primary" | "info" | "warning" | "danger" | "neutral" => {
  switch (status) {
    case "completed":
      return "success";
    case "failed":
      return "danger";
    case "running":
    case "uploading":
      return "primary";
    case "cancelling":
    case "cancelled":
      return "warning";
    case "pending":
    case "queued":
      return "info";
    default:
      return "neutral";
  }
};

export default function TrainingJobProjectPage() {
  const { workspaceId = "", jobId = "" } = useParams();
  const navigate = useNavigate();
  const { t } = useTranslation("training");
  const query = useQuery({
    queryKey: ["training", "workspace-job", workspaceId, jobId],
    queryFn: () => getWorkspaceJob(workspaceId, jobId),
  });
  const back = () =>
    navigate(`/dashboard/training/workspaces/${workspaceId}/job/${jobId}`);
  const job = query.data;
  return (
    <section className="space-y-5">
      <PageHeader title={t("studio.assignProject")} back onBack={back} />
      {query.isError ? (
        <div role="alert">
          <p>{getApiErrorMessage(query.error, t("studio.failed"))}</p>
          <Button onClick={() => void query.refetch()}>
            {t("studio.reload")}
          </Button>
        </div>
      ) : !job ? (
        <p role="status">{t("studio.loading")}</p>
      ) : job.status !== "completed" ||
        !job.output_available ||
        job.deletion_pending ? (
        <p>{t("studio.noOutput")}</p>
      ) : (
        <TrainingJobProjectForm key={job.id} job={job} />
      )}
    </section>
  );
}

type RequirementsMode = "none" | "from_input" | "upload";

function TrainingJobProjectForm({ job }: { job: TrainingJob }) {
  const { t } = useTranslation("training");
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const suggestedProject = params.get("project") ?? undefined;
  const onBack = () =>
    navigate(
      `/dashboard/training/workspaces/${job.workspace_id}/job/${job.id}`,
    );
  const inputQuery = useQuery({
    queryKey: ["training", "input", job.id],
    queryFn: () => getRunInput(job.id),
    staleTime: Infinity,
  });
  const [inputModes, setInputModes] = useState<Record<string, string>>({});
  const [inputChoices, setInputChoices] = useState<Record<string, string>>({});
  const [pendingJob, setPendingJob] = useState<string | null>(null);
  const jobsQuery = useQuery({
    queryKey: ["training", "assignment-jobs", job.workspace_id],
    queryFn: () => listAllWorkspaceJobs(job.workspace_id),
    enabled: Boolean(job.workspace_id),
  });
  const selectJob = (id: string) =>
    navigate(
      `/dashboard/training/workspaces/${job.workspace_id}/job/${id}/project`,
    );
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
    setInputModes(
      Object.fromEntries(
        ["source_code", "reference_data"].map((kind) => [
          kind,
          outputQuery.data?.[kind as "source_code" | "reference_data"]
            ? "upload"
            : "none",
        ]),
      ),
    );
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
  const [requirementsMode, setRequirementsMode] =
    useState<RequirementsMode>("from_input");
  const [requirementsFile, setRequirementsFile] = useState<File | null>(null);
  const [buildRequirements, setBuildRequirements] = useState<string | null>(
    null,
  );
  const project = projects?.models.find((item) => item.id === projectId);

  const accessOptions = [
    {
      value: "private" as const,
      title: t("createFlow.metadata.privateTitle"),
      description: t("createFlow.metadata.privateDescription"),
    },
    {
      value: "public" as const,
      title: t("createFlow.metadata.publicTitle"),
      description: t("createFlow.metadata.publicDescription"),
    },
  ];

  const originalRequirements =
    outputQuery.data?.build_requirements_text ??
    job.requirements_text ??
    "";
  const effectiveRequirements =
    requirementsMode === "none"
      ? ""
      : (buildRequirements ?? originalRequirements);
  const requirementsChanged =
    effectiveRequirements !== originalRequirements ||
    Boolean(requirementsFile);

  async function save() {
    setBusy(true);
    try {
      let output = outputQuery.data;
      if (!output) throw new Error(t("studio.reload"));
      const supplementalFiles = { ...files };
      for (const kind of ["source_code", "reference_data"] as const) {
        if (inputModes[kind] === "input") {
          const path = inputChoices[kind];
          if (!path) throw new Error(t("studio.reload"));
          const { blob } = await downloadWorkspaceSelection(
            job.id,
            "input",
            path,
          );
          supplementalFiles[kind] = new File([blob], path.split("/").pop()!, {
            type: kind === "source_code" ? "text/x-python" : "text/csv",
          });
        }
      }
      if (
        ["source_code", "reference_data"].some((kind) =>
          Boolean(supplementalFiles[kind]),
        ) ||
        removed.length ||
        requirementsChanged
      ) {
        output = await patchModelOutput(job.id, {
          output_revision: output.output_revision,
          source_code_file: supplementalFiles.source_code,
          reference_data_file: supplementalFiles.reference_data,
          remove_assets: removed,
          ...(requirementsChanged
            ? { build_requirements_text: effectiveRequirements }
            : {}),
        });
        queryClient.setQueryData(outputKey, output);
        setRemoved([]);
        setBuildRequirements(null);
        setRequirementsFile(null);
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
      queryClient.setQueryData(
        ["training", "workspace-job", job.workspace_id, assigned.id],
        assigned,
      );
      queryClient.setQueryData(trainingQueryKeys.job(assigned.id), assigned);
      void queryClient.invalidateQueries({ queryKey: ["training"] });
      void queryClient.invalidateQueries({ queryKey: ["models"] });
      navigate("/dashboard/training");
    } catch (error) {
      if (isTrainingRevisionConflict(error)) setConflict(true);
      toast.error(getApiErrorMessage(error, t("studio.failed")));
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="space-y-6">
      <div className="space-y-8 rounded-surface border border-border bg-surface p-6 shadow-sm">
        {/* Group 1: Training Run Source */}
        <section className="space-y-4">
          <Title
            title={t("assignment.sourceTitle")}
            description={t("assignment.sourceDescription")}
          />
          <Select
            label={t("workspaceHistory.jobId")}
            value={job.id}
            disabled={busy || jobsQuery.isLoading || jobsQuery.isError}
            options={(jobsQuery.data ?? [job]).map((item) => ({
              value: item.id,
              label: item.id,
              hint: (
                <Badge variant={getJobStatusVariant(item.status)}>
                  {t(`detail.statuses.${item.status}`)}
                </Badge>
              ),
              disabled:
                item.status !== "completed" ||
                !item.output_available ||
                item.deletion_pending,
            }))}
            onChange={(id) => {
              if (id === job.id) return;
              const saved = outputQuery.data?.selection;
              const dirty =
                Object.values(files).some(Boolean) ||
                removed.length > 0 ||
                Object.values(inputChoices).some(Boolean) ||
                ["source_code", "reference_data"].some(
                  (kind) =>
                    (inputModes[kind] ?? "none") !==
                    (outputQuery.data?.[kind as "source_code" | "reference_data"]
                      ? "upload"
                      : "none"),
                ) ||
                requirementsChanged ||
                name !== "" ||
                description !== "" ||
                access !== "private" ||
                projectId !== (job.project_id ?? suggestedProject ?? "new") ||
                modelId !== (saved?.model_id ?? "") ||
                slots.some(
                  (slot) =>
                    (choices[slot] ?? "") !== (saved?.artifacts?.[slot] ?? "") ||
                    (modes[slot] ?? "none") !==
                      (saved?.artifacts?.[slot] ? "metadata" : "none"),
                );
              if (dirty) setPendingJob(id);
              else selectJob(id);
            }}
          />
          {jobsQuery.isError && (
            <Button onClick={() => void jobsQuery.refetch()}>
              {t("studio.reload")}
            </Button>
          )}
          <ConfirmDialog
            open={Boolean(pendingJob)}
            title={t("studio.unsaved")}
            description={t("studio.discard")}
            onCancel={() => setPendingJob(null)}
            onConfirm={() => {
              if (pendingJob) selectJob(pendingJob);
            }}
          />
        </section>

        <hr className="border-border" />

        {/* Group 2: Target Model Project */}
        <section className="space-y-4">
          <Title
            title={t("assignment.projectTitle")}
            description={t("assignment.projectDescription")}
          />
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
            <div className="space-y-4">
              <Input
                id="target-project-name"
                label={t("studio.name")}
                value={name}
                disabled={busy}
                placeholder={t("createFlow.metadata.namePlaceholder")}
                onChange={(event) => setName(event.target.value)}
              />
              <TextArea
                id="target-project-description"
                label={t("studio.description")}
                value={description}
                disabled={busy}
                placeholder={t("createFlow.metadata.descriptionPlaceholder")}
                onChange={(value) => setDescription(value)}
              />
              <Picker
                title={t("studio.access")}
                value={access}
                disabled={busy}
                onChange={(value) => setAccess(value)}
                options={accessOptions}
              />
            </div>
          ) : (
            <div className="space-y-4">
              <Input
                id="target-project-name"
                label={t("studio.name")}
                value={project?.name ?? ""}
                readOnly
                disabled
              />
              <TextArea
                id="target-project-description"
                label={t("studio.description")}
                value={project?.description ?? ""}
                readOnly
                disabled
              />
              <Picker
                title={t("studio.access")}
                value={
                  (project?.access_mode as "private" | "public") ?? "private"
                }
                disabled
                onChange={() => {}}
                options={accessOptions}
              />
              <Callout
                variant="info"
                title={t("studio.metadataReadOnly")}
              />
            </div>
          )}
        </section>

        <hr className="border-border" />

        {/* Group 3: Model Artifacts & Metadata */}
        <section className="space-y-4">
          <Title
            title={t("assignment.artifactsTitle")}
            description={t("assignment.artifactsDescription")}
          />
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
          </div>
        </section>

        <hr className="border-border" />

        {/* Group 4: Code & Data */}
        <section className="space-y-4">
          <Title
            title={t("assignment.codeDataTitle")}
            description={t("assignment.codeDataDescription")}
          />
          <div className="grid gap-4 md:grid-cols-2">
            {(["source_code", "reference_data"] as const).map((kind) => {
              const mode = inputModes[kind] ?? "none";
              const existing = !removed.includes(kind) && outputQuery.data?.[kind];
              return (
                <div key={kind} className="space-y-2">
                  <Select
                    label={t(`studio.${kind}`)}
                    value={mode}
                    disabled={busy}
                    options={[
                      { value: "none", label: t("studio.artifactSelection.none") },
                      {
                        value: "input",
                        label: t(`studio.artifactSelection.${kind}Input`),
                      },
                      {
                        value: "upload",
                        label: t(`studio.artifactSelection.${kind}Upload`),
                      },
                    ]}
                    onChange={(value) => {
                      setInputModes((old) => ({ ...old, [kind]: value }));
                      setInputChoices((old) => ({ ...old, [kind]: "" }));
                      setFiles((old) => ({ ...old, [kind]: null }));
                      setRemoved((old) =>
                        value === "none" && outputQuery.data?.[kind]
                          ? [...new Set([...old, kind])]
                          : old.filter((item) => item !== kind),
                      );
                    }}
                  />
                  {mode === "input" && (
                    <>
                      <Select
                        aria-label={t(`studio.artifactSelection.${kind}Input`)}
                        placeholder={t(`studio.artifactSelection.${kind}Input`)}
                        value={inputChoices[kind] ?? ""}
                        disabled={
                          busy || inputQuery.isLoading || inputQuery.isError
                        }
                        options={(inputQuery.data?.entries ?? [])
                          .filter(
                            (entry) =>
                              entry.kind !== "folder" &&
                              entry.path
                                .toLowerCase()
                                .endsWith(kind === "source_code" ? ".py" : ".csv"),
                          )
                          .map((entry) => ({
                            value: entry.path,
                            label: entry.path,
                          }))}
                        onChange={(value) =>
                          setInputChoices((old) => ({ ...old, [kind]: value }))
                        }
                      />
                      {inputQuery.isError && (
                        <Button onClick={() => void inputQuery.refetch()}>
                          {t("studio.reload")}
                        </Button>
                      )}
                    </>
                  )}
                  {mode === "upload" && (
                    <FileDropzone
                      accept={kind === "source_code" ? ".py" : ".csv"}
                      title={
                        files[kind]?.name ??
                        (existing
                          ? existing.name
                          : t(`studio.artifactSelection.${kind}Upload`))
                      }
                      subtitle={t("studio.optionalArtifact")}
                      hasFile={Boolean(files[kind] || existing)}
                      disabled={busy}
                      onRemove={() => {
                        setFiles((old) => ({ ...old, [kind]: null }));
                        if (outputQuery.data?.[kind])
                          setRemoved((old) => [...new Set([...old, kind])]);
                      }}
                      onChange={(file) => {
                        setFiles((old) => ({ ...old, [kind]: file }));
                        setRemoved((old) => old.filter((item) => item !== kind));
                      }}
                    />
                  )}
                </div>
              );
            })}
          </div>
        </section>

        <hr className="border-border" />

        {/* Group 5: Requirements */}
        <section className="space-y-4">
          <Title
            title={t("assignment.requirementsTitle")}
            description={t("assignment.requirementsDescription")}
          />
          <Select
            label={t("assignment.requirementsSelectLabel")}
            value={requirementsMode}
            disabled={busy}
            options={[
              { value: "none", label: t("assignment.requirementsNone") },
              {
                value: "from_input",
                label: t("assignment.requirementsFromInput"),
              },
              {
                value: "upload",
                label: t("assignment.requirementsUpload"),
              },
            ]}
            onChange={(val) => {
              const mode = val as RequirementsMode;
              setRequirementsMode(mode);
              if (mode === "none") {
                setBuildRequirements("");
                setRequirementsFile(null);
              } else if (mode === "from_input") {
                setBuildRequirements(
                  outputQuery.data?.build_requirements_text ??
                    job.requirements_text ??
                    "",
                );
                setRequirementsFile(null);
              } else if (mode === "upload") {
                setBuildRequirements(requirementsFile ? buildRequirements : "");
              }
            }}
          />
          {requirementsMode === "upload" && (
            <FileDropzone
              accept=".txt,text/plain"
              disabled={busy}
              title={
                requirementsFile?.name ?? t("assignment.uploadRequirements")
              }
              subtitle={t("assignment.uploadRequirementsHint")}
              hasFile={Boolean(requirementsFile)}
              onRemove={() => {
                setRequirementsFile(null);
                setBuildRequirements("");
              }}
              onChange={(file) => {
                setRequirementsFile(file);
                if (file) {
                  void file
                    .text()
                    .then((content) => setBuildRequirements(content));
                }
              }}
            />
          )}
          {requirementsMode !== "none" && (
            <TextArea
              id="build-requirements"
              label={t("studio.buildRequirements")}
              disabled={busy}
              value={effectiveRequirements}
              onChange={(value) => setBuildRequirements(value)}
              placeholder={"scikit-learn==1.7.2\npandas==2.2.1\nnumpy==1.26.4"}
              minHeight="min-h-36"
            />
          )}
        </section>

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
                setInputModes(
                  Object.fromEntries(
                    ["source_code", "reference_data"].map((kind) => [
                      kind,
                      result.data?.[kind as "source_code" | "reference_data"]
                        ? "upload"
                        : "none",
                    ]),
                  ),
                );
                setInputChoices({});
                setFiles({});
                setRemoved([]);
                setRequirementsMode("from_input");
                setRequirementsFile(null);
                setBuildRequirements(null);
                setConflict(false);
              });
            }}
          >
            {t("studio.reload")}
          </Button>
        )}
      </div>

      <div className="grid grid-cols-2 gap-4">
        <Button
          type="button"
          variant="secondary"
          fullWidth
          disabled={busy}
          onClick={onBack}
        >
          {t("studio.back")}
        </Button>
        <Button
          type="button"
          fullWidth
          loading={busy}
          disabled={
            conflict ||
            !outputQuery.data?.can_edit ||
            !modelId ||
            ["source_code", "reference_data"].some((kind) =>
              inputModes[kind] === "input"
                ? !inputChoices[kind] ||
                  inputQuery.isError ||
                  inputQuery.isLoading
                : inputModes[kind] === "upload"
                  ? !files[kind] &&
                    (!outputQuery.data?.[
                      kind as "source_code" | "reference_data"
                    ] ||
                      removed.includes(kind))
                  : false,
            ) ||
            slots.some((slot) =>
              modes[slot] === "metadata"
                ? !choices[slot]
                : modes[slot] === "upload"
                  ? !files[slot] ||
                    files[slot].size > 1024 * 1024 ||
                    !files[slot].name.toLowerCase().endsWith(".json")
                  : false,
            ) ||
            (requirementsMode === "upload" &&
              !requirementsFile &&
              !effectiveRequirements.trim()) ||
            (projectId === "new" && !name.trim())
          }
          onClick={() => void save()}
        >
          {t("studio.save")}
        </Button>
      </div>
    </div>
  );
}
