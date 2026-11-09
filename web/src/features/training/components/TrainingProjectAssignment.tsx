import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { listModelProjects } from "@/shared/api/catalogApi";
import { Button } from "@/shared/components/Button";
import { Input } from "@/shared/components/Input";
import { FileDropzone } from "@/shared/components/FileDropzone";
import { getApiErrorMessage } from "@/shared/api/errors";
import { toast } from "@/shared/lib/toastStore";
import type { TrainingJob } from "@/features/training/types";
import { assignTrainingProject } from "@/features/training/api/workspacesApi";
import { getModelOutputSummary, patchModelOutput } from "@/features/training/api/trainingApi";

export function TrainingProjectAssignment({ job, suggestedProject, onBack, onSaved }: { job: TrainingJob; suggestedProject?: string; onBack: () => void; onSaved: (job: TrainingJob) => void }) {
  const { t } = useTranslation("training");
  const queryClient = useQueryClient();
  const outputKey = ["training", "assignment-output", job.id];
  const outputQuery = useQuery({ queryKey: outputKey, queryFn: () => getModelOutputSummary(job.id), staleTime: Infinity, refetchOnWindowFocus: false });
  const { data: projects } = useQuery({ queryKey: ["training", "assignment-projects"], queryFn: listModelProjects });
  const [projectId, setProjectId] = useState(job.project_id ?? suggestedProject ?? "new");
  const [newId] = useState(() => crypto.randomUUID());
  const [name, setName] = useState(""); const [description, setDescription] = useState("");
  const [access, setAccess] = useState<"private" | "public">("private");
  const [busy, setBusy] = useState(false);
  const [files, setFiles] = useState<Record<string, File | null>>({});
  const [removed, setRemoved] = useState<string[]>([]);
  const [buildRequirements, setBuildRequirements] = useState<string | null>(null);
  const project = projects?.models.find((item) => item.id === projectId);
  async function save() {
    setBusy(true);
    try {
      let output = outputQuery.data;
      if (!output) throw new Error(t("studio.reload"));
      if (Object.values(files).some(Boolean) || removed.length || buildRequirements !== null) {
        output = await patchModelOutput(job.id, { output_revision: output.output_revision,
          source_code_file: files.source_code, reference_data_file: files.reference_data,
          label_mapping_file: files.label_mapping, input_schema_file: files.input_schema,
          remove_assets: removed,
          ...(buildRequirements !== null ? { build_requirements_text: buildRequirements } : {}) });
        queryClient.setQueryData(outputKey, output);
        setFiles({}); setRemoved([]); setBuildRequirements(null);
      }
      const assigned = await assignTrainingProject(job.id, output.output_revision, projectId === "new" ?
        { new_project: { id: newId, name, description, access_mode: access } } : { project_id: projectId });
      onSaved(assigned);
    } catch (error) { toast.error(getApiErrorMessage(error, t("studio.failed"))); }
    finally { setBusy(false); }
  }
  return <section className="space-y-5 rounded-surface border border-border bg-surface p-5">
    <h2 className="text-style-section-title">{t("studio.assignProject")}</h2>
    <p className="text-style-body text-color-muted-foreground">{t("studio.assignmentHint")}</p>
    <label className="block space-y-2 text-style-body-strong"><span>{t("studio.project")}</span>
      <select className="h-12 w-full rounded-control border border-input bg-surface px-3" value={projectId} disabled={busy || Boolean(job.project_id)} onChange={(event) => setProjectId(event.target.value)}>
        <option value="new">{t("studio.newProject")}</option>
        {projects?.models.filter((item) => item.is_active).map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
      </select>
    </label>
    {projectId === "new" ? <>
      <Input label={t("studio.name")} value={name} disabled={busy} onChange={(event) => setName(event.target.value)} />
      <Input label={t("studio.description")} value={description} disabled={busy} onChange={(event) => setDescription(event.target.value)} />
      <label className="block space-y-2 text-style-body-strong"><span>{t("studio.access")}</span><select className="h-12 w-full rounded-control border border-input bg-surface px-3" value={access} disabled={busy} onChange={(event) => setAccess(event.target.value as "private" | "public")}><option value="private">{t("studio.private")}</option><option value="public">{t("studio.public")}</option></select></label>
    </> : <div className="rounded-surface border border-border p-4 text-style-body"><p>{project?.name}</p><p>{project?.description}</p><p>{project?.access_mode}</p><p className="mt-2 text-color-muted-foreground">{t("studio.metadataReadOnly")}</p></div>}
    <div className="grid gap-4 md:grid-cols-2">
      {(["source_code", "reference_data", "label_mapping", "input_schema"] as const).map((kind) => <FileDropzone key={kind} accept={kind === "source_code" ? ".py" : kind === "reference_data" ? ".csv" : ".json"} title={files[kind]?.name ?? (!removed.includes(kind) ? outputQuery.data?.[kind]?.name : null) ?? t(`studio.${kind}`)} subtitle={t("studio.optionalArtifact")} hasFile={Boolean(files[kind] || (!removed.includes(kind) && outputQuery.data?.[kind]))} disabled={busy} onRemove={() => { setFiles((current) => ({ ...current, [kind]: null })); setRemoved((current) => [...current, kind]); }} onChange={(file) => { setFiles((current) => ({ ...current, [kind]: file })); if (file) setRemoved((current) => current.filter((item) => item !== kind)); }} />)}
    </div>
    <label className="block space-y-2 text-style-body-strong"><span>{t("studio.buildRequirements")}</span><textarea className="min-h-28 w-full rounded-control border border-input bg-surface p-3 font-mono text-style-body" value={buildRequirements ?? outputQuery.data?.build_requirements_text ?? job.requirements_text} disabled={busy} onChange={(event) => setBuildRequirements(event.target.value)} /></label>
    {outputQuery.isError && <Button variant="secondary" onClick={() => void outputQuery.refetch()}>{t("studio.reload")}</Button>}
    <div className="flex justify-between gap-3"><Button variant="secondary" disabled={busy} onClick={onBack}>{t("studio.back")}</Button><Button loading={busy} disabled={!outputQuery.data || (projectId === "new" && !name.trim())} onClick={() => void save()}>{t("studio.save")}</Button></div>
  </section>;
}
